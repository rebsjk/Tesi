# Passive flows — design and role in the thesis

Status: **universe chosen, fields confirmed for all 4 tickers (2026-07-04).**
This note documents why a passive-flows block is included, the instrument
universe chosen, and how the derived flow variables should be constructed
for use in Phase 4/6 regressions.

## Role in the thesis

Passive/ETF flows are **not** a P-measure or a Q-measure input, and do
not define a new numbered build phase. They are an auxiliary,
mechanism-test variable that enters existing Phase 4 (physical-risk) and
Phase 6 (integration) regressions as a control or interaction term:

1. As a control alongside CSI in downside-risk / skew / VRP / tail-premia
   regressions.
2. As a mechanism test: whether high concentration combined with strong
   passive inflows produces a stronger effect than concentration alone.
3. As an aggregate proxy for mechanical/passive demand pressure on the
   S&P 500 benchmark, and — via the cap-weighted vs. equal-weighted
   contrast below — a proxy for how much of that pressure is
   concentration-sensitive.

The core P-vs-Q comparison does not depend on this block. It is included
because it gives the concentration-as-state-variable story an explicit
transmission-channel test, not because it is required to answer the
thesis's central question.

## Instrument universe

**SPY US Equity, IVV US Equity, VOO US Equity, RSP US Equity.**

The first three are the dominant cap-weighted S&P 500 ETFs and together
account for the large majority of ETF AUM tracking the index used
throughout this thesis. RSP (Invesco S&P 500 Equal Weight ETF) holds the
same 500 constituents at equal weight, giving a same-universe,
different-weighting counterfactual — directly mirroring the
HHI-vs-effective-N directionality distinction already used in the CSI
construction (see `csi_construction.md`).

A broader universe (UCITS cross-listings, sector/factor ETFs, mutual
fund share classes) was considered and explicitly **not** pursued for
the baseline: cross-currency and cross-timezone alignment, hedged vs.
unhedged share classes, and lower-frequency mutual-fund flow reporting
would each add a layer of aggregation choices that are hard to defend
individually and would dilute focus from the thesis's central
contribution. This remains a documented possible extension, not a
silent omission.

## Field status

`FUND_TOTAL_ASSETS` (AUM) and `FUND_FLOW` (net flow, isolates flow from
price-return effects on AUM) are confirmed non-blank for all 4 tickers
(SPY terminal check 2026-07-02; IVV/VOO/RSP terminal check 2026-07-04).
Confirmed history start (first non-blank date, both fields), each
essentially at fund inception:

| Ticker | First non-blank date | Observed frequency |
|---|---|---|
| SPY US Equity | 1993-01-29 | Daily, no gaps (spot-checked recent 27-trading-day window) |
| IVV US Equity | 2000-05-22 | Daily, no gaps |
| VOO US Equity | 2010-09-09 | Daily, no gaps |
| RSP US Equity | 2003-04-29 | Daily, no gaps |

No field-blank or share-class reporting issues found for any of the 4
tickers. The one design-relevant consequence: **VOO's history only
starts in 2010**, materially later than SPY/IVV. Any aggregate
cap-weighted series (SPY+IVV+VOO) is therefore an unbalanced panel
before 2010-09-09 — sum only SPY+IVV before that date and add VOO from
its inception, rather than backfilling or NaN-filling it. This does not
change the design (SPY+IVV alone already cover the large majority of
cap-weighted S&P 500 ETF AUM pre-2010), but must be handled explicitly
in the aggregation code, and stated in the thesis text so the sample
composition change is not silently absorbed into the series.

## Derived variables

All constructed downstream of the raw `data_raw/bloomberg/bloomberg_passive_flows_<date>.csv`
pull, following the same point-in-time discipline as the CSI (any
normalization/standardization statistic used at date *t* uses only a
trailing or expanding window ending at *t*, never the full sample):

- **Aggregate cap-weighted inflow**: sum of `FUND_FLOW` across SPY,
  IVV, VOO (same currency, same underlying benchmark — directly
  summable).
- **Flow / AUM**: `flow_t / aum_{t-1}` per fund (AUM lagged one period
  to avoid scaling by an AUM already inflated by the contemporaneous
  flow), aggregated across SPY/IVV/VOO as an AUM-weighted average, not
  a simple average.
- **Cap-weighted minus equal-weighted flow**: aggregate CW flow/AUM
  minus RSP flow/AUM, expressed in normalized (%) terms — never as a
  raw dollar difference, given the large AUM gap between the two
  groups.
- **Rolling / standardized flows**: trailing rolling window (e.g.
  21 trading days) applied to flow/AUM before standardization, to
  smooth daily creation/redemption and settlement-timing noise.
  Standardization must use a trailing/expanding window only, per the
  same anti-look-ahead rule as the CSI.

## Frequency

Pulled at daily granularity (native Bloomberg resolution for both
fields), but aggregated to weekly or monthly before use as a regression
variable — raw daily flow is noisy due to ETF settlement mechanics, and
monthly aggregation aligns with the typical cadence of the Phase 4/6
regressions this variable feeds.

## Scope

ETF-only for the baseline. Mutual fund / index fund share classes are
excluded by design, not oversight: ETFs have the most direct
authorized-participant creation/redemption mechanism (the cleanest
proxy for mechanical demand pressure) and the best Bloomberg flow-data
granularity.
