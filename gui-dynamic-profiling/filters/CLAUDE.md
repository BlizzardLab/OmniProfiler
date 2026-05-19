# CLAUDE.md — filters/

Extensible global filter package that pre-filters the DataFrame for all tabs. Filters are self-registering modules: each calls `register()` at import time to add itself to `FILTER_REGISTRY`. The filter panel UI and callback logic iterate the registry, so adding a new filter requires only creating a module and importing it.

## Architecture

Two filter categories:

- **Value filters** — multi-select dropdown; `apply_filter(df, values)` keeps rows matching selected values. Located directly under `filters/`.
- **Semantic filters** — toggle switch (checklist); `apply_filter(df, value)` performs complex cross-row analysis. Located under `filters/semantic/`.

Data flow: raw cached dataset → each filter's `apply_filter()` in registry order → `set_filtered_df()` → tab callbacks call `get_filtered_df()`.

## Files

### `registry.py` — FilterDef Class & FILTER_REGISTRY

Defines the `FilterDef` dataclass (filter_id, label, category, make_component, apply_filter, get_options) and the `FILTER_REGISTRY` list. Provides `register()` to add filters.

- **Public**: `FilterDef`, `FILTER_REGISTRY`, `register()`

### `__init__.py` — Package Init & Filtered-DF Cache

Imports all filter modules (value filters directly, semantic filters via the `semantic` sub-package) to trigger registration. Maintains the module-level `_filtered_df` cache and exposes `get_filtered_df()` / `set_filtered_df()`.

- **Public**: `FILTER_REGISTRY`, `get_filtered_df()`, `set_filtered_df()`

### `resource_type.py` — Resource Type Value Filter

Multi-select dropdown filtering by `resource_type` column. Options from `store_data["resource_types"]`.

### `thread.py` — Thread Value Filter

Multi-select dropdown filtering by `thread_label` column. Options from `store_data["thread_labels"]`.

### `function_name.py` — Function Name Value Filter

Searchable multi-select dropdown filtering by `function_name` column. Shows top 200 functions by event count.

## Subdirectories

### `semantic/` — Semantic Filters Sub-package

Non-trivial filters that perform complex cross-row analysis (grouping, sorting, cross-row checks). Contains the No-USE-After-RELEASE toggle filter. See `semantic/CLAUDE.md` for details.

## Adding a New Filter

**Value filter** (simple column matching):
1. Create `filters/my_filter.py` with `_component()`, `_apply()`, and optionally `_options()`.
2. Call `register(FilterDef(..., category="value", ...))` at module level.
3. Add `import filters.my_filter` to `filters/__init__.py`.

**Semantic filter** (complex cross-row logic):
1. Create `filters/semantic/my_filter.py` with `_component()`, `_apply()`, and optionally `_options()`.
2. Call `register(FilterDef(..., category="semantic", ...))` at module level.
3. Add `import filters.semantic.my_filter` to `filters/semantic/__init__.py`.

No other changes needed — the filter panel and callback auto-discover registered filters.

## Protocol

Every edition on any Python script in this directory must be reflected (i.e., updated) in:
1. The **script's own header docstring** — keep Responsibilities, Public functions sections accurate.
2. **This CLAUDE.md** — update the corresponding file's description to match the new behaviour.
3. **Check if there are any tasks required by this CLAUDE.md** — if this file lists pending tasks or requirements, address them as part of the edit.

Every modification on this CLAUDE.md should be reflected (i.e., updated) in the CLAUDE.md in its parent directory, recursively if applicable.
