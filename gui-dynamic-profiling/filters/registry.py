"""Filter registry — FilterDef class and global filter registration.

Responsibilities:
    - Define the FilterDef dataclass that describes a single global filter.
    - Maintain the FILTER_REGISTRY list of all registered filters.
    - Provide register() to add filters and lookup helpers.

Public functions / objects:
    FilterDef              — dataclass for filter definitions
    FILTER_REGISTRY        — ordered list of registered FilterDef instances
    register(filter_def)   — append a FilterDef to the registry

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class FilterDef:
    """Definition for a single global filter.

    Attributes:
        filter_id:      Unique identifier (e.g. "resource_type").
        label:          Human-readable label for the UI.
        category:       "value" (multi-select dropdown) or "semantic" (toggle).
        make_component: Callable returning a Dash component with
                        id={"type": "global-filter", "index": filter_id}.
        apply_filter:   Callable (df, value) -> filtered DataFrame.
        get_options:    Callable (store_data) -> list of dropdown options,
                        or None for semantic (toggle) filters.
    """
    filter_id: str
    label: str
    category: str
    make_component: Callable
    apply_filter: Callable
    get_options: Optional[Callable] = None


FILTER_REGISTRY: list[FilterDef] = []


def register(filter_def: FilterDef) -> None:
    """Append a FilterDef to the global registry."""
    FILTER_REGISTRY.append(filter_def)
