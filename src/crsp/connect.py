"""
WRDS connection helper for the CSI thesis, CRSP pulls.

Mirrors the pattern in notebooks/00_setup/wrds_connectivity_check.py:
wrds.Connection() prompts for a username on stdin even when .pgpass already
holds the password for this host (it only skips the *password* prompt), so
we pass wrds_username explicitly (from the WRDS_USERNAME env var, default
"rebenassi" for this project) to keep pulls non-interactive.

Usage:
    from src.crsp.connect import get_connection
    db = get_connection()
    try:
        df = db.raw_sql("select * from crsp.dsp500list_v2 limit 10")
    finally:
        db.close()
"""

import os

import wrds

DEFAULT_WRDS_USERNAME = "rebenassi"


def get_connection(wrds_username: str | None = None) -> wrds.Connection:
    """Return a non-interactive wrds.Connection using .pgpass credentials."""
    username = wrds_username or os.environ.get("WRDS_USERNAME", DEFAULT_WRDS_USERNAME)
    return wrds.Connection(wrds_username=username)
