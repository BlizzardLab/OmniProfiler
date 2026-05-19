# Dynamic Profiling Explorer

Interactive visualization tool for exploring dynamic profiling data collected from instrumented C/C++ applications (currently MySQL/InnoDB). It helps developers identify performance bottlenecks through timeline heatmaps, statistical analysis, and bottleneck analysis.

## Architecture

```
dynamic-profiling/
├── app.py                     # Entry point — CLI parsing, Dash server, tab routing
├── data_loader.py             # Data ingestion — JSON parsing into pandas DataFrame
├── layouts/                   # Dash layout components (UI structure, no logic)
│   ├── __init__.py
│   ├── main_layout.py         # Top-level page: header, summary banner, tab container
│   ├── timeline.py            # Timeline Heatmap tab controls and graph containers
│   ├── statistics.py          # Statistics tab filters, charts, and table containers
├── callbacks/                 # Dash callbacks (interactivity logic)
│   ├── __init__.py
│   ├── data_callbacks.py      # Data loading, caching, summary banner updates
│   ├── timeline_cb.py         # Timeline heatmap rendering and click-to-detail
│   ├── statistics_cb.py       # Statistics charts, function table, time filtering
├── data-example/              # Example profiling dataset (26 threads, 9 resource types)
│   ├── dynamic-profiling-data/  # Per-thread event JSON files
│   ├── global_resource_mapping.json
│   ├── global_function_mapping.json
│   ├── index.json
│   └── README.md              # Full data format specification
├── docs/
│   └── components.md          # Component reference documentation
├── README.md
└── CLAUDE.md
```

## Quick Start

```bash
# Activate conda environment
conda activate XXXX

# Install dependencies
pip install dash plotly pandas

# Run with example data (opens browser automatically)
python app.py ./data-example

# Or run without args and load data via the browser UI
python app.py
```

The app launches at `http://127.0.0.1:8050` and opens a browser automatically.

## Features

### Timeline Heatmap
Visualizes event density across threads over time as color-coded heatmaps. One subplot per event category (USE, RELEASE, ACQUIRE, WAIT, ACCESS, GET), each with a distinct color scale. Supports filtering by resource type, toggling event categories, and adjusting time bin granularity. Click any cell to drill down into individual events.

### Statistics
Provides aggregate views of the profiling data:
- **Event Counts by Resource Type** — grouped bar chart broken down by event type
- **Top Functions by Event Count** — sortable table showing hotspot functions with unique address counts and thread spread
- **Events per Thread** — horizontal bar chart for thread activity comparison

All charts respond to resource type, thread, and time window filters.

### Global Controls
- **Time Unit Toggle** (ms/s) in the summary banner, applied across all tabs
- **Data Directory Input** for loading different datasets at runtime

## Data Format

| File | Description |
|------|-------------|
| `dynamic-profiling-data/thread_{pid}_{tid}.json` | Per-thread event traces keyed by resource type index |
| `global_resource_mapping.json` | Resource type name to integer index |
| `global_function_mapping.json` | Mangled function name to integer index |
| `index.json` | Function metadata: demangled names, parameters, resource flags |

Each event contains: `event` (USE/RELEASE/ACQUIRE/WAIT/ACCESS/GET, may be comma-separated), `function_index`, `is_exit`, `ptr` (resource address), `ts_ns` (nanosecond timestamp).
