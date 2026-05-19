# CLAUDE.md — callbacks/

Dash callback modules that wire user interactions (clicks, dropdown changes, slider drags) to UI updates. Each module provides a `register_*_callbacks(app)` function called by `app.py` at startup.

## Files

### `data_callbacks.py` — Data Loading & Caching

Manages dataset loading triggered by the Load button, caches the full dataset (DataFrame + mappings) at module level to avoid serializing large objects through `dcc.Store`, and renders the summary banner. Provides `preload_data()` for CLI pre-loading.

- **Public**: `get_cached_dataset()`, `set_cached_dataset()`, `preload_data()`, `register_data_callbacks()`
- **Callbacks** (2): `load_data` (load-btn -> data-store), `update_summary` (data-store + time-unit-toggle -> summary-banner)

### `filter_cb.py` — Global Filter Application

Pattern-matching callback that reacts to any `{"type": "global-filter"}` component value change. Iterates `FILTER_REGISTRY`, applies each filter's `apply_filter(df, value)` in sequence, caches the result via `set_filtered_df()`, and increments `filtered-data-version` to trigger downstream tab callbacks. Also populates value filter dropdown options when `data-store` changes.

- **Public**: `register_filter_callbacks()`
- **Callbacks** (2): `apply_filters` (global-filter ALL + data-store -> filtered-data-version), `populate_options` (data-store -> global-filter ALL options)

### `timeline_cb.py` — Timeline Heatmap

Renders per-event-type heatmap subplots (USE / RELEASE / ACQUIRE / WAIT / ACCESS / GET) using vectorized NumPy binning. Each event appears in every subplot whose category it contains (e.g. "RELEASE, USE" in both). Handles click-to-detail drill-down: clicking a cell shows only events matching the specific event type subplot that was clicked (via customdata). Uses `get_filtered_df()` and re-fires on `filtered-data-version` changes.

- **Public**: `register_timeline_callbacks()`
- **Callbacks** (3): resource dropdown population, heatmap rendering (with filtered-data-version), click-detail table

### `statistics_cb.py` — Statistics

Produces the resource bar chart (grouped by event type), function hotspot DataTable (top 30 by event count with unique address count, thread count, and resource types with their operation types), per-thread horizontal bar chart, WAIT Duration Flamegraph (pairs WAIT entry/exit events using backward analysis to handle ringbuffer cutoff, assigns overlapping intervals to stacked layers via greedy sweep-line, draws horizontal bars colored by resource type; orphan WAITs are extended to thread end and highlighted with a yellow border), and WAIT hotspot DataTable (top 30 functions by total WAIT wall-time with pair count, unique addresses, thread count, and resource types with co-occurring operations). All charts honour the event type checklist, time window RangeSlider, time unit toggle, and global filters via `get_filtered_df()` and `filtered-data-version`.

- **Public**: `register_statistics_callbacks()`
- **Callbacks** (5): dropdown/slider config, resource bar, function table, thread bar, WAIT flamegraph

### `bottleneck_cb.py` — Bottleneck Analysis

Renders the Contention Scoreboard (resource type contention bar showing WAIT/addr ratio sorted descending with WAIT count and unique addresses on hover), Top Contended Addresses horizontal bar chart (driven by clicking a resource type bar; shows top 15 addresses for the clicked type ranked by total WAIT duration), and a combined Multi-Layer Cascading Contention Map + Temporal Contention Heatmap callback (both driven by resource type bar click; Sankey link values represent WAIT event pair counts with address nodes ranked by pair count descending; two-phase BFS: Phase 1 discovers associated resource types via shared functions using raw events (no WAIT interval requirement), Phase 2 computes WAIT pair counts from the full dataset and builds Sankey nodes/links; cross-layer links (new_addr→prev_func→thread) use raw event associations with the addr's WAIT pair count as value; cascade depth 0–3, per-layer explore/display sliders, min node flow filter; the temporal heatmap shows per-thread WAIT wall-time duration for Sankey entities with interval spreading, blank until a bar is clicked). Toggles visibility of per-layer slider rows based on cascade depth. Pairs WAIT entry/exit events using backward analysis (same pattern as statistics_cb.py). All charts honour resource type/thread filters, time window RangeSlider, time unit toggle, and global filters via `get_filtered_df()` and `filtered-data-version`.

- **Public**: `register_bottleneck_callbacks()`
- **Callbacks** (4 + 2 clientside): controls config, restype bar, addr bar (click-driven), cascade Sankey + temporal heatmap (arrangement="fixed"), toggle layer sliders, clientside node hover/click highlighting (both grounded in real trace `(ptr, function_name, thread_label)` triples shipped via `fig.layout.meta` — `addr_thread_funcs`, `triple_link_map`, `addr_func_thread_durations` — NOT Sankey graph reachability; hover on any node highlights only links that come from genuine triples involving the hovered node, so hovering an addr never lights up threads that share a function with it on a different addr and hovering a thread never lights up addrs the thread never reached; click on two thread nodes highlights shared resource addresses, connecting functions, and the corresponding links in red; populates a Shared Contention Functions table between the Sankey and heatmap showing per-thread function durations sorted descending, summed only over the shared addresses for each (function, thread) pair), clientside reset (clears thread selection, restores default colors, and clears the shared contention table)

## Protocol

Every edition on any Python script in this directory must be reflected (i.e., updated) in:
1. The **script's own header docstring** — keep Responsibilities, Public functions, and Dash callbacks sections accurate.
2. **This CLAUDE.md** — update the corresponding file's description to match the new behaviour.
3. **Check if there are any tasks required by this CLAUDE.md** — if this file lists pending tasks or requirements, address them as part of the edit.

Every modification on this CLAUDE.md should be reflected (i.e., updated) in the CLAUDE.md in its parent directory, recursively if applicable.