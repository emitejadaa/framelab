"""framelab — explore, transform and plot pandas DataFrames without writing code."""

__version__ = "0.0.1.dev0"

from .api import explore, last_session  # noqa: E402
from .options import get_option, options, reset_option, set_option  # noqa: E402

__all__ = [
    "__version__",
    "explore",
    "get_option",
    "last_session",
    "options",
    "reset_option",
    "set_option",
]
