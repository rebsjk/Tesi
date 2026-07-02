# Concentration State Index (CSI) — Thesis Research Project

## Core thesis

Market concentration (the degree to which index/market value is
concentrated in a small number of constituents) is treated as a
**structural state variable for systemic risk** — not just a descriptive
statistic. The empirical program builds a **Concentration State Index
(CSI)** from constituent-level weights and uses it to condition and
predict risk across two distinct measures:

- **P (physical measure)** — realized risk as observed in historical
  return data (CRSP): volatility, drawdowns, tail co-movement, systemic
  risk measures, conditioned on the CSI state.
- **Q (risk-neutral measure)** — forward-looking, market-implied risk
  priced into options (Bloomberg options chains): implied volatility
  surfaces, risk-neutral skewness/kurtosis, tail risk premia, conditioned
  on the CSI state.

**P and Q must never be silently blended.** Every dataset, script, and
notebook in this project should make it unambiguous which measure it
belongs to. The central empirical question is whether concentration
*priced* in the Q-measure (what the market fears) and concentration
*realized* in the P-measure (what actually happens) move together, lead
one another, or diverge — that comparison is the payoff of the thesis, and
it only works if P and Q are built independently before being compared.

## Priority build order

The project is built in this order. Do not start a later phase using
placeholder/incomplete output from an earlier one — CSI, physical-risk, and
Q-tail work all depend on the universe panel being correct first.

1. **Constituent universe** — membership, weights, and returns
   (`notebooks/01_universe/`, `src/universe/`, `data_final/universe/`)
2. **Concentration measures** — individual, separately computed metrics
   (`notebooks/02_concentration/`, `src/concentration/`,
   `data_final/concentration/`)
3. **CSI construction** — aggregating measures into the composite state
   index (`notebooks/03_csi/`, `src/csi/`, `data_final/csi/`)
4. **Physical-risk econometrics (P)** — realized-risk models conditioned on
   CSI (`notebooks/04_physical_risk/`, `src/physical_risk/`,
   `data_final/physical_risk/`)
5. **Options and risk-neutral tails (Q)** — implied-risk models conditioned
   on CSI (`notebooks/05_options_tails/`, `src/options_tails/`,
   `data_final/options_tails/`)
6. **Integration and robustness** — joint P-vs-Q tests, subperiod/crisis
   robustness, alternative CSI specifications
   (`notebooks/06_integration/`, `src/integration/`,
   `data_final/integration/`)

## Directory structure

```
data_raw/            Untouched exports/downloads, exactly as received —
                      organized BY SOURCE, not by phase, since provenance
                      and re-pull reproducibility matter more here than
                      where the data is eventually used
  crsp/                 CRSP daily/monthly stock file pulls
  compustat/             Compustat fundamentals (if/when needed for controls)
  bloomberg/              Index membership, weights, prices, options chains
  optionmetrics/           OptionMetrics IvyDB chains/surfaces (if used instead
                            of or alongside Bloomberg options data)
  manual/                   Hand-entered data (index reconstitution notices, etc.)

data_interim/         Cleaned but not yet at its final phase-level shape.
                      Source-cleaned folders exist per source as they come
                      into use; phase folders hold the first cross-source
                      merge for that phase.
  bloomberg/             Source-cleaned Bloomberg data
  crsp/                  Source-cleaned CRSP data
  universe/               CRSP + Bloomberg merged into a raw constituent panel
  concentration/          Concentration measures before CSI aggregation
  options/                 Cleaned option chains before tail-measure extraction

data_final/            Analysis-ready output, one folder per build phase
  universe/               Entity-date panel: membership, weights, returns
  concentration/            Individual concentration measures panel
  csi/                       Composite CSI series + state/regime classification
  physical_risk/             P-measure realized-risk output conditioned on CSI
  options_tails/              Q-measure risk-neutral tail output conditioned on CSI
  integration/                 Joint P-vs-Q datasets, robustness output

notebooks/            Numbered to match the priority build order above
  00_setup/               Environment checks, WRDS/Bloomberg connectivity
  01_universe/             Build and QA the constituent universe panel
  02_concentration/         Compute and compare individual concentration measures
  03_csi/                    Construct and validate the composite CSI
  04_physical_risk/           P-measure econometrics
  05_options_tails/            Q-measure / options tail econometrics
  06_integration/               Joint P-vs-Q tests and robustness

src/                  Reusable, importable code (no notebook-only logic)
  bloomberg/               Bloomberg API/session wrappers, field maps
  crsp/                    WRDS connection helpers, CRSP query builders
  cleaning/                Source-agnostic cleaning utilities
  merges/                  Entity/date matching, PERMNO<->Bloomberg ID crosswalks
  universe/                Constituent panel construction (membership/weights/returns)
  concentration/            Individual concentration measure implementations
  csi/                       CSI aggregation, normalization, state/regime logic
  physical_risk/             P-measure models (realized vol, systemic risk, etc.)
  options_tails/              Q-measure models (IV surfaces, risk-neutral moments)
  integration/                 Joint P-vs-Q tests, robustness harnesses
  utils/                    Logging, config loading, path helpers, I/O helpers

docs/
  data_notes/               Per-source/per-pull notes: fields, coverage, issues
  workflow_notes/           How to run each phase's pipeline
  variable_definitions/     Canonical formula for every derived variable
  methodology_notes/         Research-design decisions: CSI construction method,
                              P/Q separation protocol, state/regime thresholds,
                              robustness protocol

outputs/
  figures/                  Generated plots
  tables/                    Generated tables (regression output, summary stats)
  logs/                       Pipeline run logs
```

## Guiding principles

- **Raw data is immutable.** Nothing under `data_raw/` is edited in place.
  Re-pull into a new dated file rather than overwrite.
- **`data_raw/` is organized by source; everything downstream of it is
  organized by phase.** This is deliberate: provenance and re-pull
  reproducibility are what matter for raw data (which vendor, which pull,
  which date), while every other stage of the pipeline is organized around
  what build phase (1-6) the output belongs to. Don't let phase folders
  bleed into `data_raw/`, and don't reorganize `data_raw/` by phase later.
- **P and Q stay in separate folders and separate scripts, always.**
  `physical_risk/` code never reads options data; `options_tails/` code
  never reads CRSP realized-return series as an input to a Q-measure
  estimate. The only place they meet is `integration/`.
- **CSI is a state variable, not a summary statistic.** It must be
  constructed to be point-in-time valid — no look-ahead in how thresholds,
  regimes, or normalization windows are estimated, since it will be used
  as a conditioning variable in both P and Q regressions downstream.
- **Every transformation is a script, not a one-off notebook edit.**
  Notebooks call functions from `src/`; they should not contain long
  inline logic.
- **Document research-design decisions as you make them**, not just data
  quirks. Concentration measure choice, CSI aggregation method, state
  thresholds, and the P/Q comparison protocol belong in
  `docs/methodology_notes/`.

## Conventions

- File naming: `<source>_<content>_<YYYYMMDD>.<ext>` for raw pulls (e.g.
  `bloomberg_index_weights_20260702.csv`).
- Every script in `src/` that produces a `data_interim/` or `data_final/`
  output logs to `outputs/logs/` with source file(s), row counts in/out,
  and timestamp.
- Every derived variable (every concentration measure, the CSI itself,
  every P- or Q-risk measure) gets an entry in `docs/variable_definitions/`
  with its exact formula, units, frequency, and source columns.

## Available subagents

See `.claude/agents/` for specialized agents for this project:

- `bloomberg-extractor` — Bloomberg pulls: index membership/weights/prices
  (phase 1) and options chains (phase 5)
- `crsp-extractor` — CRSP/WRDS pulls: returns and membership (phase 1)
- `concentration-builder` — individual concentration measures (phase 2) and
  CSI construction (phase 3)
- `data-validator` — QA at any stage, including P/Q separation and
  point-in-time validity checks
- `physical-risk-analyst` — P-measure econometrics (phase 4) and joint
  P-vs-Q integration/robustness (phase 6)
- `options-tail-analyst` — Q-measure / options tail econometrics (phase 5)
- `notebook-methods-writer` — turning notebook/src work into
  `docs/methodology_notes/`, `docs/data_notes/`, and
  `docs/variable_definitions/`
