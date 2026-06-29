# CGM Missing Simulator

Standalone package for fitting, saving, loading, and applying a statistical CGM missingness model.

Included in this folder:

- `fitted_missingness.json`: a ready-to-use fitted missingness model, currently fit from the larger DCLP3 and DCLP5 datasets
- `example.ipynb`: a short demo for masking and reconstruction

## Setup

```bash
git clone <your-repo-url>
cd <your-repo-name>/CGM_MISSING_SIMULATOR
pip install .
```

For editable install:

```bash
pip install -e .
```

## Data Format

Fitting CSVs should contain:

- `SID`
- `DT_Index`
- `Value`

Application data should contain at least:

- `date`
- `cgm`

Extra columns are preserved. Missingness is written only to `cgm_simulated`.

## Quick Use

Load the included fitted model:

```python
from cgm_missing_simulator import load_missingness_model

gen = load_missingness_model("fitted_missingness.json")
```

Fit and save a new model:

```bash
fit-cgm-missingness \
  --csv-list dclp3_cgm_plus_features.csv dclp5_cgm_plus_features.csv \
  --threshold 0.5 \
  --output fitted_missingness.json
```

Apply the model:

```python
import pandas as pd
from cgm_missing_simulator import load_missingness_model

gen = load_missingness_model("fitted_missingness.json")

df = pd.read_csv("my_cgm.csv")
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)

masked_df = gen.generate_mask(df)
```

## Main Functions

- `fit_missingness_model(...)`: fit a missingness generator from real CGM gap data
- `save_missingness_model(...)`: save a fitted model to JSON
- `load_missingness_model(...)`: load a fitted model from JSON
- `fit_and_save_missingness_model(...)`: fit and save in one step
- `generate_mask(...)`: apply missingness to a CGM DataFrame

## Example Notebook

```bash
jupyter notebook example.ipynb
```
