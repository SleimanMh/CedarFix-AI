import sys
from pathlib import Path

# Add repo root to path so service modules and data modules are importable
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
