# data_raw/crsp/ — not versioned

This directory's contents (and `data_interim/crsp/`, `data_final/universe/`)
are gitignored. The raw daily-returns pull alone is ~940MB — too large to
version — and everything here is fully reproducible from code, so there is
nothing to lose by not tracking it. If this directory looks empty apart
from `.gitkeep` and this file, that's expected, not a missing pull.

## How to regenerate

Requires the `tesi-wrds` conda environment (`wrds`, `pandas`, `sqlalchemy`,
`psycopg2`, `pyarrow`) and a working WRDS login (`.pgpass` at
`%APPDATA%\postgresql\pgpass.conf`; see
`notebooks/00_setup/wrds_connectivity_check.py` for the one-time setup).

Run these three steps in order, from the project root:

```
# 1. Raw pull from WRDS -> data_raw/crsp/
#    (edit START_DATE/END_DATE/PULL_DATE_TAG at the top of the script for
#    a fresh vintage rather than overwriting an existing dated file)
%USERPROFILE%\anaconda3\envs\tesi-wrds\python.exe src\crsp\pull_sp500_raw.py

# 2. Filter + delisting adjustment -> data_interim/crsp/
%USERPROFILE%\anaconda3\envs\tesi-wrds\python.exe src\crsp\clean_sp500_raw.py

# 3. Point-in-time membership join + weight computation -> data_final/universe/
%USERPROFILE%\anaconda3\envs\tesi-wrds\python.exe src\universe\build_constituent_panel.py
```

Each step logs row counts, coverage, and any anomalies to `outputs/logs/`.
See `docs/data_notes/crsp_sp500_raw_pull_20260819.md`,
`docs/methodology_notes/index_weight_construction.md`, and
`docs/workflow_notes/data_inventory.md` for what each field means and why
the pipeline is shaped this way (CIZ/`_v2` table family, physical-schema
access workaround, share/exchange filter, delisting-return handling,
self-computed weight).

Step 1 will refuse to overwrite an existing dated file (`data_raw/` is
immutable by convention — see CLAUDE.md) — bump the date tag for a re-pull
rather than deleting the old one first.
