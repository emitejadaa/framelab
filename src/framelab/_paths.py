"""Location of the compiled frontend bundle shipped inside the package."""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "_static"


def require_static() -> Path:
    bundle = STATIC_DIR / "framelab.js"
    if not bundle.is_file():
        raise RuntimeError(
            "framelab's frontend bundle is missing. From a source checkout run "
            "`cd frontend && mise exec -- pnpm install && mise exec -- pnpm build`."
        )
    return STATIC_DIR
