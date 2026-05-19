"""Global filter package — extensible filter registry for pre-filtering data.

Responsibilities:
    - Import value filter modules and the semantic sub-package to trigger
      their register() calls.
    - Re-export FILTER_REGISTRY, get_filtered_df(), and set_filtered_df()
      for use by callbacks and other modules.

Public objects:
    FILTER_REGISTRY          — ordered list of FilterDef instances
    get_filtered_df() -> DataFrame | None
    set_filtered_df(df) -> None

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

import pandas as pd

from filters.registry import FILTER_REGISTRY  # noqa: F401

# Module-level cache for the filtered DataFrame
_filtered_df = None


def get_filtered_df():
    """Return the globally filtered DataFrame, or None if not yet computed."""
    return _filtered_df


def set_filtered_df(df):
    """Store the globally filtered DataFrame."""
    global _filtered_df
    _filtered_df = df


# Import filter modules to trigger registration (order matters for UI layout)
import filters.resource_type       # noqa: F401, E402
import filters.thread              # noqa: F401, E402
import filters.function_name       # noqa: F401, E402
import filters.semantic               # noqa: F401, E402
