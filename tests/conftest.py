import sys
from pathlib import Path

# tests/ sits directly under the project root; put the root on sys.path so
# `from src...` imports work when running `pytest` with no extra packaging
# config (no pyproject.toml/setup.py in this project).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
