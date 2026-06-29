# CGM Missing Simulator

This folder is a standalone installable package for fitting, saving, loading, and applying a CGM missingness model from real gap statistics.

An example fitted model is already included in this folder:

- `fitted_missingness.json`

## Folder Layout

The main files in this GitHub folder are:

- `README.md`
- `pyproject.toml`
- `train_missing.py`
- `cgm_missing_simulator.py`
- `fitted_missingness.json`
- `example.ipynb`

You may also see folders like `build/`, `__pycache__/`, `.ipynb_checkpoints/`, or `*.egg-info`. Those are generated artifacts and are not required for using the package.

The notebook `example.ipynb` gives a short end-to-end example of:

- loading `fitted_missingness.json`
- injecting missingness into a sample CGM file
- reconstructing the masked CGM with linear interpolation
- plotting ground truth, observed, and imputed CGM

## Setup

First clone the repository, then move into this package folder:

```bash
git clone <your-repo-url>
cd <your-repo-name>/CGM_MISSING_SIMULATOR
```

Then install the package:

```bash
pip install .
```

For editable development:

```bash
pip install -e .
```

## What It Does

The package learns a statistical missingness model from real CGM gap data:

- hourly probability that a gap starts
- separate day/night gap-duration behavior
- JSON save/load support for the fitted generator

It does not train an imputation model.

## Included Fitted Model

The file `fitted_missingness.json` is a saved missingness model produced by this package.

The current fitted file was built from two larger CGM datasets, DCLP3 and DCLP5, which were used here for fitting.

Its purpose is to provide a ready-to-use missingness model so you can apply realistic CGM masking without running the fitting step again.

You can load it directly without refitting:

```python
from cgm_missing_simulator import load_missingness_model

gen = load_missingness_model("fitted_missingness.json")
```

This fitted model is not limited to those two datasets. You can refit the same pipeline on other datasets as long as they follow the fitting format described below. In practice, the model can be extended to other CGM datasets with the same schema, and typically benefits from larger or denser datasets because they provide richer missingness statistics.

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

## Purpose Of The Main Functions

- `fit_missingness_model(csv_list, threshold)`: fits a statistical missingness generator from one or more real CGM datasets.
- `save_missingness_model(generator, output_path, ...)`: saves a fitted generator to JSON.
- `load_missingness_model(input_path)`: loads a previously saved JSON missingness model.
- `fit_and_save_missingness_model(csv_list, threshold, output_path)`: convenience wrapper that fits and saves in one step.
- `gen.generate_mask(df)`: applies the fitted missingness model to a DataFrame and writes the masked signal into `cgm_simulated`.

## CLI Usage

After installation:

```bash
fit-cgm-missingness \
  --csv-list dclp3_cgm_plus_features.csv dclp5_cgm_plus_features.csv \
  --threshold 0.5 \
  --output fitted_missingness.json
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
        "dclp3_cgm_plus_features.csv",
        "dclp5_cgm_plus_features.csv",
    ],
    threshold=0.5,
    output_path="fitted_missingness.json",
)

gen = load_missingness_model("fitted_missingness.json")

df = pd.read_csv("my_cgm.csv")
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)

masked_df = gen.generate_mask(df)
```

## Notebook Example

After installation, you can also open and run:

```bash
jupyter notebook example.ipynb
```

The notebook provides a compact demonstration of how to apply the fitted missingness model and visualize the masked versus reconstructed CGM signal.
