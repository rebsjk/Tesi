"""Central path resolution for the CSI thesis project.

Anchored on CLAUDE.md rather than cwd or __file__ depth, so this works the
same whether called from a notebook, a script run from a subdirectory, or a
test runner.
"""

from __future__ import annotations

import re
from pathlib import Path


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "CLAUDE.md").is_file():
            return candidate
    raise FileNotFoundError(
        "Could not locate project root (no CLAUDE.md found in any parent "
        f"of {start})."
    )


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())

DATA_RAW = PROJECT_ROOT / "data_raw"
DATA_INTERIM = PROJECT_ROOT / "data_interim"
DATA_FINAL = PROJECT_ROOT / "data_final"
OUTPUTS = PROJECT_ROOT / "outputs"
DOCS = PROJECT_ROOT / "docs"

# data_raw/ is source-organized (see CLAUDE.md).
CRSP_RAW = DATA_RAW / "crsp"
COMPUSTAT_RAW = DATA_RAW / "compustat"
BLOOMBERG_RAW = DATA_RAW / "bloomberg"
OPTIONMETRICS_RAW = DATA_RAW / "optionmetrics"
MANUAL_RAW = DATA_RAW / "manual"

# data_interim/ and data_final/ are phase-organized (see CLAUDE.md).
BLOOMBERG_INTERIM = DATA_INTERIM / "bloomberg"
CRSP_INTERIM = DATA_INTERIM / "crsp"
UNIVERSE_INTERIM = DATA_INTERIM / "universe"
CONCENTRATION_INTERIM = DATA_INTERIM / "concentration"
OPTIONS_INTERIM = DATA_INTERIM / "options"

UNIVERSE_FINAL = DATA_FINAL / "universe"
CONCENTRATION_FINAL = DATA_FINAL / "concentration"
CSI_FINAL = DATA_FINAL / "csi"
PHYSICAL_RISK_FINAL = DATA_FINAL / "physical_risk"
OPTIONS_TAILS_FINAL = DATA_FINAL / "options_tails"
INTEGRATION_FINAL = DATA_FINAL / "integration"

FIGURES = OUTPUTS / "figures"
TABLES = OUTPUTS / "tables"
LOGS = OUTPUTS / "logs"

DATA_NOTES = DOCS / "data_notes"
WORKFLOW_NOTES = DOCS / "workflow_notes"
VARIABLE_DEFINITIONS = DOCS / "variable_definitions"
METHODOLOGY_NOTES = DOCS / "methodology_notes"

# Raw pull filenames follow <source>_<content>_<YYYYMMDD>.<ext> (CLAUDE.md
# conventions). Vintage lives in the filename, not in mtime, so re-pulls and
# copies stay reproducible across machines.
_DATED_FILE_RE = re.compile(r"_(\d{8})\.")


def latest_raw_file(source_dir: Path, content_prefix: str) -> Path:
    """Return the most recent dated raw file matching `content_prefix`.

    "Most recent" is determined by the YYYYMMDD embedded in the filename,
    not filesystem mtime, so this is stable across copies/checkouts.
    """
    candidates = []
    for path in source_dir.glob(f"{content_prefix}_*"):
        match = _DATED_FILE_RE.search(path.name)
        if match:
            candidates.append((match.group(1), path))

    if not candidates:
        raise FileNotFoundError(
            f"No dated files matching '{content_prefix}_*' found in {source_dir}"
        )

    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1]
