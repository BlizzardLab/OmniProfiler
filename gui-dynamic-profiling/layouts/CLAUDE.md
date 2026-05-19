# CLAUDE.md — layouts/

Dash layout modules that define the UI component tree (HTML + Dash components) for each section of the application. These modules produce static component hierarchies and contain no callback logic.

## Files

### `main_layout.py` — Top-Level Page

Root page layout: header bar with data directory input and Load button, summary banner with time unit toggle (ms/s), global filter panel, loading spinner, tab navigation (Timeline / Statistics / Bottleneck Analysis), and tab content container. Includes `filtered-data-version` dcc.Store.

- **Public**: `make_layout(initial_data_dir) -> html.Div`
- **Key IDs**: `data-store`, `filtered-data-version`, `data-dir-input`, `load-btn`, `summary-banner`, `time-unit-toggle`, `filter-panel`, `main-tabs`, `tab-content`

### `filter_panel.py` — Global Filter Panel

Renders all registered global filters from `FILTER_REGISTRY`. Value filters (dropdowns) appear in a horizontal row; semantic filters (toggles) appear in a separate section below. Uses pattern-matching IDs: `{"type": "global-filter", "index": <filter_id>}`.

- **Public**: `filter_panel_layout() -> html.Div`
- **Key IDs**: `filter-panel`, `{"type": "global-filter", "index": <filter_id>}`

### `timeline.py` — Timeline Heatmap Tab

Resource type dropdown, event type checklist (USE / RELEASE / ACQUIRE / WAIT / ACCESS / GET), time bin slider, heatmap graph container (no fixed CSS height; figure controls its own size). Below the heatmap, a click-detail panel. Container is invisible when empty; max-height scroll keeps the populated panel bounded.

- **Public**: `timeline_layout() -> html.Div`
- **Key IDs**: `timeline-resource-dropdown`, `timeline-event-checklist`, `timeline-bins-slider`, `timeline-heatmap`, `timeline-detail`

### `statistics.py` — Statistics Tab

Resource type and thread dropdown filters, event type checklist (USE / RELEASE / ACQUIRE / WAIT / ACCESS / GET), time window RangeSlider with dynamic label, resource bar chart, function hotspot DataTable container, per-thread bar chart, WAIT Duration Flamegraph (horizontal bar chart of WAIT intervals stacked by overlap layer, colored by resource type, with orphan WAIT support), and WAIT hotspot DataTable (top functions by total WAIT wall-time).

- **Public**: `statistics_layout() -> html.Div`
- **Key IDs**: `stats-resource-dropdown`, `stats-thread-dropdown`, `stats-event-checklist`, `stats-time-range`, `stats-time-label`, `stats-resource-bar`, `stats-function-table`, `stats-thread-bar`, `stats-wait-flamegraph`, `stats-wait-table`

### `bottleneck.py` — Bottleneck Analysis Tab

Resource type and thread dropdown filters, time window RangeSlider with dynamic label, time bins slider, Contention Scoreboard (resource type contention bar chart, top contended addresses horizontal bar chart), Temporal Contention Heatmap (per-thread WAIT wall-time duration for Sankey entities; blank until a resource type bar is clicked), and Multi-Layer Cascading Contention Map (Sankey diagram with BFS expansion from clicked resource type through shared functions to collateral resource types; cascade depth dropdown 0–3, per-layer explore/display sliders controlling BFS expansion vs. display count, min node flow filter removing nodes with too few connections, layer slider rows shown/hidden based on depth). Includes a Reset button (`bottleneck-cascade-reset`) to clear thread-pair click-highlight selection, and a hidden dummy div (`bottleneck-hover-dummy`) used as output target for clientside callbacks.

- **Public**: `bottleneck_layout() -> html.Div`
- **Key IDs**: `bottleneck-resource-dropdown`, `bottleneck-thread-dropdown`, `bottleneck-time-range`, `bottleneck-time-label`, `bottleneck-bins-slider`, `bottleneck-restype-bar`, `bottleneck-addr-bar`, `bottleneck-temporal-heatmap`, `bottleneck-cascade-depth`, `bottleneck-cascade-min-flow`, `bottleneck-cascade-reset`, `bottleneck-cascade-explore-0..3`, `bottleneck-cascade-display-0..3`, `bottleneck-cascade-row-0..3`, `bottleneck-cascade-sankey`, `bottleneck-hover-dummy`

## Protocol

Every edition on any Python script in this directory must be reflected (i.e., updated) in:
1. The **script's own header docstring** — keep Responsibilities, Public functions, and Dash component IDs sections accurate.
2. **This CLAUDE.md** — update the corresponding file's description to match the new behaviour.
3. **Check if there are any tasks required by this CLAUDE.md** — if this file lists pending tasks or requirements, address them as part of the edit.

Every modification on this CLAUDE.md should be reflected (i.e., updated) in the CLAUDE.md in its parent directory, recursively if applicable.
