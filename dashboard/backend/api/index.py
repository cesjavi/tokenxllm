# api/index.py
import sys
from pathlib import Path

# añade el root del repo al PYTHONPATH para poder importar dashboard.*
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# importa tu FastAPI real
from dashboard.backend.main import app  # noqa: F401
