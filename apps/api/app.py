from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT / "app"
MAIN_PATH = PACKAGE_ROOT / "main.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

spec = spec_from_file_location("aeo_api_main", MAIN_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load FastAPI app from {MAIN_PATH}")

module = module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app
