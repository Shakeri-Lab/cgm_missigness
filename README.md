# CGM Missing Simulator

This folder is a standalone installable package for fitting, saving, loading, and applying a CGM missingness model from real gap statistics.

An example fitted model is already included in this folder:

- `CGM_MISSING_SIMULATOR/fitted_missingness.json`

## Install

From the repository root:

```bash
pip install ./CGM_MISSING_SIMULATOR
```

For editable development:

```bash
pip install -e ./CGM_MISSING_SIMULATOR
```

## What It Does

The package learns a statistical missingness model from real CGM gap data:

- hourly probability that a gap starts
- separate day/night gap-duration behavior
- JSON save/load support for the fitted generator

It does not train an imputation model.

## Included Fitted Model

The file `fitted_missingness.json` is a saved missingness model produced by this package. You can load it directly without refitting:

```python
from cgm_missing_simulator import load_missingness_model

gen = load_missingness_model("CGM_MISSING_SIMULATOR/fitted_missingness.json")
```

## Saved JSON Format

The saved model JSON has this structure:

```json
{
  "version": 1,
  "metadata": {
    "csv_list": ["..."],
    "valid_threshold": 0.5
  },
  "generator": {
    "hourly_probs": [24 values],
    "day_prob_single": 0.0,
    "day_mix": [A, k, B, mu, sigma, C],
    "night_prob_single": 0.0,
    "night_mix": [A, k, B, mu, sigma, C]
  }
}
```

Meaning of the fields:

- `hourly_probs`: probability that a gap starts in each hour from `0` to `23`
- `day_prob_single`: probability of a 5-minute single-point gap during daytime
- `day_mix`: fitted daytime duration-mixture parameters
- `night_prob_single`: probability of a 5-minute single-point gap during nighttime
- `night_mix`: fitted nighttime duration-mixture parameters

## Fitting Data Format

The CSV files used for fitting should contain:

- `SID`: subject identifier
- `DT_Index`: timestamp
- `Value`: CGM value

Example:

```csv
SID,DT_Index,Value
1001,2024-01-01 00:00:00,112
1001,2024-01-01 00:05:00,111
1001,2024-01-01 00:10:00,
```

## Application Data Format

To apply the fitted mask later with `generate_mask(...)`, your DataFrame should contain at least:

- `date`
- `cgm`

Example:

```csv
date,cgm,meal,bolus
2024-01-01 00:00:00,112,0,0
2024-01-01 00:05:00,111,0,0
2024-01-01 00:10:00,109,0,0
```

Extra columns are preserved. Only `cgm_simulated` is modified.

## CLI Usage

After installation:

```bash
fit-cgm-missingness \
  --csv-list RawData/dclp3_cgm_plus_features.csv RawData/dclp5_cgm_plus_features.csv \
  --threshold 0.5 \
  --output CGM_MISSING_SIMULATOR/fitted_missingness.json
```

## Python Usage

```python
import pandas as pd

from cgm_missing_simulator import (
    fit_and_save_missingness_model,
    load_missingness_model,
)

fit_and_save_missingness_model(
    [
        "RawData/dclp3_cgm_plus_features.csv",
        "RawData/dclp5_cgm_plus_features.csv",
    ],
    threshold=0.5,
    output_path="CGM_MISSING_SIMULATOR/fitted_missingness.json",
)

gen = load_missingness_model("CGM_MISSING_SIMULATOR/fitted_missingness.json")

df = pd.read_csv("my_cgm.csv")
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)

masked_df = gen.generate_mask(df)
```
