"""Semantic filter sub-package — non-trivial filters with cross-row analysis.

Responsibilities:
    - Import all semantic filter modules to trigger their register() calls.

Semantic filters perform complex logic (grouping, sorting, cross-row checks)
rather than simple value matching. Each module self-registers via the shared
FilterDef registry in filters.registry.

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

import filters.semantic.no_use_after_release  # noqa: F401
