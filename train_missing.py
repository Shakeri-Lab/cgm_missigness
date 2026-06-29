import argparse
import json
import os

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.stats import truncnorm

class MISSINGNESS_PATTERN:
    def __init__(self, datapath_list, target_col='Value'):
        self.df = pd.concat([pd.read_csv(csv) for csv in datapath_list], axis=0, ignore_index=True)
        
        self.df['DT_Index'] = pd.to_datetime(self.df['DT_Index'])
        self.target_col = target_col
        self.df[self.target_col] = pd.to_numeric(self.df[self.target_col], errors='coerce')
        
    def resampling(self):
        def enforce_5min(group):
            group = group.drop_duplicates(subset='DT_Index')
            group = group.set_index('DT_Index')
            group = group.sort_index()

            if group.empty: return group

            start_time = group.index.min().floor('D')
            end_time = group.index.max().ceil('D') - pd.Timedelta(minutes=5)
            full_grid = pd.date_range(start=start_time, end=end_time, freq='5min', name='DT_Index')
            
            return group.reindex(full_grid)

        df_regular = self.df.groupby('SID').apply(enforce_5min)        
        
        if 'SID' in df_regular.columns: df_regular = df_regular.drop(columns=['SID'])
        df_regular = df_regular.reset_index()
        if 'DT_Index' not in df_regular.columns and 'level_1' in df_regular.columns:
            df_regular = df_regular.rename(columns={'level_1': 'DT_Index'})
            
        return df_regular

    def filter_valid_days(self, df, threshold=0.50):
        """ Removes 'Ghost Days' (low adherence) so they don't corrupt the gap analysis. """
        expected_points = 288
        min_required = expected_points * threshold
        
        df_clean = df.copy()
        df_clean['Date'] = df_clean['DT_Index'].dt.date
        
        daily_counts = df_clean.groupby(['SID', 'Date'])[self.target_col].count()
        valid_days = daily_counts[daily_counts >= min_required].index
        
        df_clean = df_clean.set_index(['SID', 'Date'])
        df_filtered = df_clean.loc[df_clean.index.isin(valid_days)].reset_index()
        
        return df_filtered

    def analyze_gaps(self, rs_df):
        """ Find missing block starting point with its length. """
        gap_data = []
        for sid, grp in rs_df.groupby('SID'):
            mask = grp[self.target_col].isna()
            blocks = (mask != mask.shift()).cumsum()
            
            gap_summary = grp[mask].groupby(blocks).agg(
                Start_Time=('DT_Index', 'first'),
                Count=('DT_Index', 'size')
            )
            
            gap_summary['Duration_Min'] = gap_summary['Count'] * 5
            gap_summary['SID'] = sid
            gap_summary['Hour_of_Day'] = gap_summary['Start_Time'].dt.hour
            gap_summary['Date'] = gap_summary['Start_Time'].dt.date
            
            gap_data.append(gap_summary)

        if gap_data:
            return pd.concat(gap_data).reset_index(drop=True)
        else:
            return pd.DataFrame()

    def analyze_hourly_profile(self, gap_stats, df_clean):
        """ Probablity of hours gaps begin. """
        M = df_clean[['SID', 'Date']].drop_duplicates().shape[0]
        day_hour = gap_stats[['SID', 'Date', 'Hour_of_Day']].drop_duplicates()
        Nh_days = day_hour['Hour_of_Day'].value_counts().sort_index()    
        p = (Nh_days / M).reindex(range(24), fill_value=0)
        return p.clip(upper=1.0)

    @staticmethod
    def mixture_func(x, A, k, B, mu, sigma, C):
        """ Curve formulation. """
        exp_part = A * np.exp(-k * (x - 10))
        gauss_part = B * np.exp(-((x - mu)**2) / (2 * sigma**2))
        return exp_part + gauss_part + C
        
    def fit_regime_distribution(self, gaps, regime='day'):
        """ Fits separate distributions for Day vs. Night. """
        if regime == 'night':
            subset = gaps[(gaps['Hour_of_Day'] >= 0) & (gaps['Hour_of_Day'] < 6)]
        else:
            subset = gaps[(gaps['Hour_of_Day'] >= 6)]

        all_data = subset['Duration_Min'].values
        valid = all_data[(all_data == 5) | ((all_data >= 10) & (all_data <= 240))]
        if len(valid) == 0: return 0, None
        prob_single = np.sum(valid == 5) / len(valid)
        tail_data = valid[valid >= 10]
        
        if len(tail_data) < 10: return prob_single, None

        counts, bin_edges = np.histogram(tail_data, bins=np.arange(10, 245, 5), density=True)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        mix_params = self._fit_curve(regime, np.max(counts), self.mixture_func, bin_centers, counts)
        return prob_single, mix_params

    
    def _fit_curve(self, regime, max_density, mixture_func, bin_centers, counts): 
        """ Help function for fitting curve. """
        if regime == 'day':
            A_guess, k_guess = counts[0], 0.02
            B_guess = counts[(np.abs(bin_centers - 120)).argmin()] * 3
            p0 = [A_guess, k_guess, B_guess, 120, 1, 0.001]
            bounds = ([0, 0.001, 0, 118, 1, 0], [np.inf, 0.2, B_guess, 122, 2, 0.01])
        else:
            p0 = [max_density, 0.05, max_density/10, 30, 10, 0.001]            
            bounds = ([0, 0.001, 0, 10, 5, 0], [np.inf, 0.2, np.inf, 240, 60, 0.01])
        try:
            mix_params = curve_fit(mixture_func, bin_centers, counts, p0=p0, bounds=bounds, maxfev=10000)[0]
            print(f"{regime.capitalize()} Fit Success: mu={mix_params[3]:.2f}, sigma={mix_params[4]:.2f}")
        except (RuntimeError, ValueError):
            print(f"{regime.capitalize()} fit failed.")
            mix_params = None
        return mix_params

class RealisticMaskGenerator:
    def __init__(self, hourly_rate, day_params, night_params):
        """
        day_params / night_params: Tuple of (prob_single, mix_params)
        """
        self.hourly_probs = hourly_rate.values if hasattr(hourly_rate, 'values') else hourly_rate
        
        self.day_prob_single, self.day_mix = day_params
        self.night_prob_single, self.night_mix = night_params
        
        self.day_areas = self._calc_areas(self.day_mix) if self.day_mix is not None else None
        self.night_areas = self._calc_areas(self.night_mix) if self.night_mix is not None else None

    @staticmethod
    def _truncnorm(mu, sigma, lo, hi):
        a, b = (lo - mu) / sigma, (hi - mu) / sigma
        return truncnorm.rvs(a, b, loc=mu, scale=sigma)
    
    @staticmethod
    def _snap5(x, lo=10, hi=240):
        x = float(x)
        x = min(max(x, lo), hi)
        return 5.0 * int(round(x / 5.0))
    
    def _calc_areas(self, params, lo=10, hi=240, step=5):
        """ Integral of curve. """
        A, k, B, mu, sigma, C = params
        x = np.arange(lo, hi + step, step)
    
        exp_part = A * np.exp(-k * (x - lo))
        gauss_part = B * np.exp(-((x - mu)**2) / (2 * sigma**2))
        unif_part = C * np.ones_like(x)
    
        Z = (exp_part + gauss_part + unif_part).sum()
        p_exp = exp_part.sum() / Z
        p_gauss = gauss_part.sum() / Z
    
        return (p_exp, p_gauss, params, lo, hi)



    def sample_duration(self, hour):
        """ Decides duration based on Time of Day (Regime Switching). """
        is_night = (hour < 6)
        prob_single = self.night_prob_single if is_night else self.day_prob_single
        mix_data = self.night_areas if is_night else self.day_areas
        if np.random.rand() < prob_single: return 5.0        
        if mix_data is not None:
            p_exp, p_gauss, params, lo, hi = mix_data
            A, k, B, mu, sigma, C = params
            r = np.random.rand()
            if r < p_exp:
                duration = 10 + np.random.exponential(scale=(1 / k))
                duration = min(max(duration, lo), hi) 
            elif r < (p_exp + p_gauss):
                duration = self._truncnorm(mu, sigma, lo, hi)
            else:
                duration = 5 * np.random.randint(lo//5, (hi//5) + 1)
            
            return self._snap5(float(duration), lo=lo, hi=hi)
        
        return 10.0

    def _compute_mask_array(self, dt_series):
        """ Returns a boolean NumPy array where True = Missing. """
        total_points = len(dt_series)
        drop_mask = np.zeros(total_points, dtype=bool)        
        hours = dt_series.dt.hour.values 
        
        current_idx = 0
        while current_idx < total_points:
            current_hour = hours[current_idx]
            hour_end_idx = current_idx
            while hour_end_idx < total_points and hours[hour_end_idx] == current_hour: hour_end_idx += 1
            if np.random.rand() < self.hourly_probs[current_hour]:                
                duration_mins = self.sample_duration(current_hour)
                duration_points = int(round(duration_mins / 5))
                
                if duration_points > 0:
                    points_in_hour = hour_end_idx - current_idx
                    start_offset = np.random.randint(0, points_in_hour)
                    
                    abs_start = current_idx + start_offset
                    abs_end = min(abs_start + duration_points, total_points)                    
                    drop_mask[abs_start : abs_end] = True
                    current_idx = abs_end 
                    continue 

            current_idx = hour_end_idx
            
        return drop_mask

    def generate_mask(self, df_slice):
        """ Applies the calculated mask to the DataFrame. """  
        df_slice = df_slice.copy()
        if 'cgm_simulated' not in df_slice.columns: 
            df_slice['cgm_simulated'] = df_slice['cgm'].copy()
            
        dt_series = pd.to_datetime(df_slice['date'])
        if dt_series.empty: return df_slice
        
        drop_mask = self._compute_mask_array(dt_series)        
        if 'cgm_simulated' in df_slice.columns: 
            df_slice.loc[drop_mask, 'cgm_simulated'] = np.nan
            
        return df_slice

    def to_state(self):
        """Serialize the fitted generator so it can be saved and reused later."""
        return {
            "hourly_probs": [float(x) for x in np.asarray(self.hourly_probs, dtype=float).tolist()],
            "day_prob_single": float(self.day_prob_single),
            "day_mix": None if self.day_mix is None else [float(x) for x in self.day_mix],
            "night_prob_single": float(self.night_prob_single),
            "night_mix": None if self.night_mix is None else [float(x) for x in self.night_mix],
        }

    @classmethod
    def from_state(cls, state):
        """Rebuild a fitted generator from a saved JSON-compatible state."""
        hourly_probs = np.asarray(state["hourly_probs"], dtype=float)
        day_mix = None if state.get("day_mix") is None else tuple(float(x) for x in state["day_mix"])
        night_mix = None if state.get("night_mix") is None else tuple(float(x) for x in state["night_mix"])

        day_params = (float(state["day_prob_single"]), day_mix)
        night_params = (float(state["night_prob_single"]), night_mix)
        return cls(hourly_probs, day_params, night_params)

    def save(self, output_path, metadata=None):
        """Save the fitted missingness model to disk as JSON."""
        payload = {
            "version": 1,
            "metadata": metadata or {},
            "generator": self.to_state(),
        }
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(payload, f, indent=4)

    @classmethod
    def load(cls, input_path):
        """Load a fitted missingness model from disk."""
        with open(input_path, "r") as f:
            payload = json.load(f)
        state = payload.get("generator", payload)
        return cls.from_state(state)


def init_train_masking(csv_list, threshold):
    """ Init training real-world masking with Day/Night splitting. """
    
    pipeline = MISSINGNESS_PATTERN(csv_list)
    df_resampled = pipeline.resampling()
    df_clean = pipeline.filter_valid_days(df_resampled, threshold=threshold)
    gaps = pipeline.analyze_gaps(df_clean)
    hourly_rate = pipeline.analyze_hourly_profile(gaps, df_clean)
    
    day_params = pipeline.fit_regime_distribution(gaps, regime='day')
    night_params = pipeline.fit_regime_distribution(gaps, regime='night')
    
    gen = RealisticMaskGenerator(hourly_rate, day_params, night_params)
    return gen


def fit_missingness_model(csv_list, threshold):
    """Fit the missingness generator from one or more real CGM CSV files."""
    return init_train_masking(csv_list, threshold)


def save_missingness_model(generator, output_path, csv_list=None, threshold=None):
    """Persist a fitted missingness generator so future runs can reuse it."""
    metadata = {}
    if csv_list is not None:
        metadata["csv_list"] = list(csv_list)
    if threshold is not None:
        metadata["valid_threshold"] = float(threshold)
    generator.save(output_path, metadata=metadata)


def load_missingness_model(input_path):
    """Load a previously saved missingness generator."""
    return RealisticMaskGenerator.load(input_path)


def fit_and_save_missingness_model(csv_list, threshold, output_path):
    """Convenience helper for one-shot fitting and saving."""
    generator = fit_missingness_model(csv_list, threshold)
    save_missingness_model(generator, output_path, csv_list=csv_list, threshold=threshold)
    return generator


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Fit a realistic missingness model from real CGM gap statistics and save it for later reuse."
    )
    parser.add_argument(
        "--csv-list",
        nargs="+",
        required=True,
        help="One or more CSV files used to fit the missingness model.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Minimum valid-day coverage threshold used before fitting. Default: 0.5",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the JSON file where the fitted missingness model will be saved.",
    )
    return parser.parse_args()


def main():
    """CLI entry point for fitting and saving a missingness model."""
    args = _parse_args()
    generator = fit_and_save_missingness_model(args.csv_list, args.threshold, args.output)
    print(f"Saved fitted missingness model to: {args.output}")
    print(f"Hourly probabilities learned for {len(generator.hourly_probs)} hours")


if __name__ == "__main__":
    main()
