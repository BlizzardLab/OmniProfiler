# CLAUDE.md — filters/semantic/

Sub-package for non-trivial (semantic) filters that perform complex cross-row analysis rather than simple value matching. Each module self-registers via the shared FilterDef registry. Adding a new semantic filter requires creating a module here and importing it from `filters/semantic/__init__.py`.

## Files

### `__init__.py` — Sub-package Init

Imports all semantic filter modules to trigger their `register()` calls.

### `no_use_after_release.py` — No USE After RELEASE Semantic Filter

Toggle that removes RELEASE events followed by a USE on the same ptr address (non-final releases). Groups by ptr, sorts by ts_ns, and checks for subsequent USE events.

## Adding a New Semantic Filter

1. Create `filters/semantic/my_filter.py` with `_component()`, `_apply()`, and optionally `_options()`.
2. Call `register(FilterDef(..., category="semantic", ...))` at module level.
3. Add `import filters.semantic.my_filter` to `filters/semantic/__init__.py`.
4. No other changes needed — the filter panel and callback auto-discover registered filters.

## Protocol

Every edition on any Python script in this directory must be reflected (i.e., updated) in:
1. The **script's own header docstring** — keep Responsibilities, Public functions sections accurate.
2. **This CLAUDE.md** — update the corresponding file's description to match the new behaviour.
3. **Check if there are any tasks required by this CLAUDE.md** — if this file lists pending tasks or requirements, address them as part of the edit.

Every modification on this CLAUDE.md should be reflected (i.e., updated) in the CLAUDE.md in its parent directory, recursively if applicable.
