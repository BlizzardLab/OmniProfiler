# Component Reference

This document describes each module in the project, its responsibilities, public interface, and the Dash component IDs or callback I/O it manages.

---

## `app.py` — Entry Point

**Purpose**: Application entry point. Parses CLI arguments, creates the Dash app, registers all layouts and callbacks, and launches the development server.

**Public Interface**:

| Function | Signature | Description |
|----------|-----------|-------------|
| `create_app` | `(data_dir: str = "") -> Dash` | Creates and configures the Dash app. If `data_dir` is provided, pre-loads the dataset. Registers all callbacks and the tab-switching logic. |
| `main` | `() -> None` | CLI entry point. Reads `sys.argv` for an optional data directory (defaults to `./data-example`), calls `create_app`, opens the browser, and starts the server on port 8050. |

**Callback**: `main-tabs.value` -> `tab-content.children` (tab switching)

---

## `data_loader.py` — Data Ingestion

**Purpose**: Reads all JSON files from a profiling data directory and produces a unified pandas DataFrame along with lookup maps.

**Public Interface**:

| Function | Signature | Description |
|----------|-----------|-------------|
| `load_dataset` | `(directory_path: str) -> dict` | Loads `global_resource_mapping.json`, `global_function_mapping.json`, `index.json`, and all `thread_*.json` files. Returns a dict containing the DataFrame (`df`), resource/function maps, thread list, and time range. |

**DataFrame columns**: `thread_id`, `process_id`, `resource_type`, `resource_type_idx`, `event`, `function_index`, `function_name`, `is_exit`, `ptr`, `ts_ns`, `ts_relative_ns`, `has_use`, `has_release`, `has_acquire`, `has_wait`， `has_access`, `has_get`, `thread_label`

**Return dict keys**: `df`, `resource_map`, `resource_map_rev`, `function_index_to_name`, `function_metadata`, `threads`, `time_range_ns`

---

## `layouts/` — UI Layout Components

Layout modules define the Dash component tree (HTML + Dash components) for each section of the app. They contain no callback logic.

### `layouts/main_layout.py` — Top-Level Page

**Purpose**: Defines the root page layout: header bar with data directory input, summary banner with time unit toggle, tab navigation, and tab content container.

| Function | Signature | Description |
|----------|-----------|-------------|
| `make_layout` | `(initial_data_dir: str = "") -> html.Div` | Builds the full page layout. Pre-fills the directory input if `initial_data_dir` is provided. |

**Dash IDs**: `data-store`, `initial-data-dir`, `data-dir-input`, `load-btn`, `summary-banner`, `time-unit-toggle`, `loading-indicator`, `loading-target`, `main-tabs`, `tab-content`

### `layouts/timeline.py` — Timeline Heatmap Tab

**Purpose**: Layout for the Timeline Heatmap tab. Provides resource type dropdown, event type checklist, time bin slider, heatmap graph, and detail table container.

| Function | Signature | Description |
|----------|-----------|-------------|
| `timeline_layout` | `() -> html.Div` | Returns the timeline tab layout. |

**Dash IDs**: `timeline-resource-dropdown`, `timeline-event-checklist`, `timeline-bins-slider`, `timeline-heatmap`, `timeline-detail`

### `layouts/statistics.py` — Statistics Tab

**Purpose**: Layout for the Statistics tab. Provides resource/thread dropdowns, time range slider, resource bar chart, function hotspot table, and per-thread bar chart.

| Function | Signature | Description |
|----------|-----------|-------------|
| `statistics_layout` | `() -> html.Div` | Returns the statistics tab layout. |

**Dash IDs**: `stats-resource-dropdown`, `stats-thread-dropdown`, `stats-time-range`, `stats-time-label`, `stats-resource-bar`, `stats-function-table`, `stats-thread-bar`

---

## `callbacks/` — Interactivity Logic

Callback modules register Dash callbacks that respond to user interactions (dropdown changes, clicks, slider drags) and update the UI accordingly.

### `callbacks/data_callbacks.py` — Data Loading & Caching

**Purpose**: Manages dataset loading triggered by the Load button, caches the dataset in a module-level variable, and updates the summary banner. Provides a pre-load path for CLI usage.

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_cached_dataset` | `() -> dict` | Returns the currently cached dataset dict (or empty dict). |
| `set_cached_dataset` | `(dataset: dict) -> None` | Replaces the cached dataset. |
| `preload_data` | `(directory_path: str) -> dict` | Loads data and caches it. Returns a JSON-serializable store summary. |
| `register_data_callbacks` | `(app, initial_store_data=None) -> None` | Registers the load-data and summary-banner callbacks on the Dash app. |

**Callbacks**:
- `load-btn.n_clicks` + `data-dir-input.value` -> `data-store.data`, `loading-target.children`
- `data-store.data` + `time-unit-toggle.value` -> `summary-banner.children`

### `callbacks/timeline_cb.py` — Timeline Heatmap

**Purpose**: Renders the per-event-type heatmap subplots with vectorized binning (`np.add.at`). Handles click-to-detail for drilling into individual events in a time/thread cell.

| Function | Signature | Description |
|----------|-----------|-------------|
| `register_timeline_callbacks` | `(app) -> None` | Registers heatmap, resource dropdown, and detail-table callbacks. |

**Callbacks**:
- `data-store.data` -> `timeline-resource-dropdown.options`
- `data-store.data` + filters + `time-unit-toggle.value` -> `timeline-heatmap.figure`
- `timeline-heatmap.clickData` + filters -> `timeline-detail.children`

### `callbacks/statistics_cb.py` — Statistics

**Purpose**: Produces the resource bar chart, function hotspot table, and per-thread bar chart. Supports filtering by resource type, thread, and a time window range slider.

| Function | Signature | Description |
|----------|-----------|-------------|
| `register_statistics_callbacks` | `(app) -> None` | Registers all statistics tab callbacks. |

**Callbacks**:
- `data-store.data` + `time-unit-toggle.value` -> dropdown options, time range slider config, `stats-time-label.children`
- `data-store.data` + filters -> `stats-resource-bar.figure`
- `data-store.data` + filters -> `stats-function-table.children`
- `data-store.data` + filters -> `stats-thread-bar.figure`
