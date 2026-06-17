from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent / "app"

# Vercel imports this file as module name "app". Expose it as a package too,
# so imports like "app.api.routes" resolve against the real app/ directory.
__path__ = [str(PACKAGE_ROOT)]

from app.main import app as fastapi_app

app = fastapi_app
