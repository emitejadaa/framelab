"""framelab — explore, transform and plot pandas DataFrames without writing code."""

__version__ = "0.0.1.dev0"

from .api import autosaves, explore, last_session, open  # noqa: E402, A004
from .options import get_option, options, reset_option, set_option  # noqa: E402

__all__ = [
    "__version__",
    "autosaves",
    "explore",
    "get_option",
    "last_session",
    "open",
    "options",
    "reset_option",
    "set_option",
]
