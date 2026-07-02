# Membership interval convention

This document defines the single canonical shape that all index-membership
data must be converted into before it reaches
`src/universe/build_constituent_panel.py`, and how to convert whatever
Bloomberg actually hands us into that shape. Every phase-1 pull ultimately
answers to this document — if a raw membership file doesn't fit one of the
raw shapes described here, extend this document before writing conversion
code, don't invent a third convention ad hoc inside a notebook.

## Canonical form

One row per `(entity_id, weight, start_date, end_date)`, **half-open on
`[start_date, end_date)`**:

- `start_date` is **inclusive** — the weight is effective *on* this date.
- `end_date` is **exclusive** — the weight is no longer effective *on* this
  date. It must equal the `start_date` of the entity's next interval
  (contiguous, no gap, no overlap) when the entity continues without
  interruption, or be `NaT` if the entity is still a constituent as of the
  last pull.

This is not an arbitrary choice — `build_constituent_panel.py` already
implements it (`merge_asof(..., direction="backward")` plus a strict
`date < end_date` filter), and its own `_check_membership_interval_structure`
check will hard-fail on overlapping intervals. This document exists so the
convention is decided and verified *before* raw data is converted, rather
than discovered as a bug after a panel is already built.

**Why half-open and not closed-inclusive-both-ends:** a closed convention
requires knowing the exact next trading day to set the outgoing interval's
last inclusive date, which depends on a trading calendar and is a second
place to get the boundary wrong. Half-open sidesteps this: the outgoing
interval's `end_date` is simply the incoming interval's `start_date`,
whatever that value is — no calendar arithmetic required.

## Raw shapes we expect from Bloomberg, and how each converts

We do not yet know which of these Bloomberg will actually give us for this
thesis's subscription tier — confirm against the terminal before writing
extraction code, and update this section once confirmed.

**Shape A — periodic weight snapshots (most likely default).**
A BDH/BDS pull of index weights at some fixed cadence (e.g. monthly, at
each scheduled rebalance) returns one row per `(as_of_date, entity_id,
weight)`, listing whichever entities were constituents as of that date. No
explicit start/end fields.

Conversion: for each `entity_id`, sort its snapshot dates ascending.
- `start_date` for a snapshot = that snapshot's `as_of_date`.
- `end_date` for a snapshot = the entity's *next* snapshot date, if the
  entity appears in it, regardless of whether the weight changed —
  intervals are defined by observation frequency, not just by membership
  events, since weight is held piecewise-constant within an interval.
- If the entity does not appear in its cadence's next index-wide snapshot,
  `end_date` = that next index-wide snapshot's date (the entity was
  dropped as of that observation; we don't know the exact intra-period
  drop date any more precisely than "somewhere before this snapshot").
- If the entity is present in the most recent snapshot pulled, `end_date`
  = `NaT` (still open).

This is an approximation: if the true reconstitution effective date falls
between two snapshot dates, the panel will misdate the boundary by up to
one snapshot period. Acceptable at monthly cadence for this thesis's
purposes; if the thesis later needs exact reconstitution-day precision,
move to Shape B.

**Shape B — explicit add/drop event log (higher fidelity, if available).**
A membership *change* history: one row per add or drop event, with an
explicit effective date. If Bloomberg's subscription includes this
(e.g. an index membership changes field rather than periodic weights),
prefer it for the membership start/end dates and pair it with a separately
pulled, possibly higher-frequency, weight series for continuing members.

Conversion: build `(entity_id, start_date)` from add events and
`(entity_id, end_date)` from the matching drop event (or `NaT` if no drop
event yet exists). Attach weight from the nearest weight observation at or
after `start_date`, forward-filled only until the next weight observation
or `end_date`, whichever is first.

**Default for this thesis:** implement Shape A first — it needs only a
standard weight pull, not a specialized membership-changes field that may
not be available. Revisit Shape B only if boundary-date precision turns
out to matter for a specific result (most likely relevant in phase 6
robustness around a specific reconstitution event, not for the baseline
CSI).

## Detecting inclusive vs. exclusive end dates in the source

Whichever raw shape we get, Bloomberg's own date field may be documented
as either "effective date" (exclusive-style: weight change takes effect
starting this date, matching our convention) or "last day of prior
weight" (inclusive-style: this is the final date the old weight held,
requiring a one-day shift before it matches our convention). Do not guess;
verify using all three of the following, in order:

1. **Field documentation, first.** Before pulling, check the exact
   Bloomberg field description (`FLDS` help text in the terminal, or the
   field's DAPI documentation) for whatever field supplies the snapshot/
   effective date. It will normally state explicitly whether the date is
   "as of" the change taking effect or the last date before the change.
   This is authoritative when available — record the field mnemonic and
   the exact wording found here once confirmed.

2. **Spot-check against a known, publicly documented reconstitution.**
   Pick 2-3 historical index changes with a public, dated press release
   (e.g. "X will replace Y in the index effective prior to the opening of
   trading on \<date\>"). Look up where in the raw pull entity X's weight
   first appears and entity Y's weight last appears, relative to the
   announced effective date:
   - If X's weight first appears exactly *on* the announced effective
     date, the source date is exclusive/effective-style — matches our
     convention directly, no shift needed.
   - If X's weight first appears the day *after* the announced effective
     date, the source date is lagged by one observation and needs
     adjustment (check whether it's a reporting lag or an
     inclusive-end-date convention on the *predecessor's* side instead).
   - Do this for at least 2-3 independent events, not one — a single
     event could coincide with a market holiday or an unrelated data gap
     and give a false read.

3. **Automated regression check, every time membership data is rebuilt.**
   `_check_membership_interval_structure()` in
   `src/universe/build_constituent_panel.py` logs the count and median
   length of gaps between consecutive same-entity intervals. A source
   using the wrong convention throughout will show up as a large number of
   *exactly one-day* gaps clustered at reconstitution dates (checked
   automatically against `outputs/logs/`, no separate script needed).
   This won't catch a wrong convention on the very first pull before any
   contiguous intervals exist to compare, which is why steps 1-2 have to
   happen first — this step is a regression guard for future re-pulls,
   not the primary detection method.

Once steps 1-2 confirm the source's convention, record the finding here
(field mnemonic, confirmed convention, and the specific events checked)
and encode any necessary date shift in the Shape A/B conversion step
above — never inside `build_constituent_panel.py` itself, which must only
ever see already-canonical, half-open data.

## Status

Not yet verified against real data — no Bloomberg pull has been made for
this project yet. Update this section (and delete this line) once step 1
and at least two step-2 spot-checks have been completed:

- Field mnemonic used: _TBD_
- Confirmed convention (inclusive / exclusive): _TBD_
- Spot-check events used: _TBD_
