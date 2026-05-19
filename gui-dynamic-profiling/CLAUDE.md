# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Interactive visualization tool for exploring dynamic profiling data collected from instrumented C/C++ applications (currently MySQL/InnoDB). The goal is to help developers identify performance bottlenecks through statistical analysis, interactive visualizations, and timeline heatmaps.

**Status**: Working prototype — Dash/Plotly web app with timeline heatmap, statistics, and bottleneck analysis tabs.

## Data Format

All profiling data lives in structured JSON files. See `data-example/README.md` for the complete specification.

### Key Files

- `data-example/dynamic-profiling-data/thread_{pid}_{tid}.json` — Per-thread event traces. Top-level keys are resource type indices (from `global_resource_mapping.json`); values are event arrays.
- `data-example/global_function_mapping.json` — Mangled function name → integer index lookup.
- `data-example/global_resource_mapping.json` — Resource type name → integer index lookup (e.g., `dict_index_t: 0`, `buf_block_t: 1`, `MDL_request: 4`).
- `data-example/index.json` — Detailed function metadata: demangled names, parameter counts, per-parameter resource flags/positions. **Warning**: this file is ~350KB; read small thread files first.

### Event Model

Each event has: `event` (USE/RELEASE/ACQUIRE/WAIT/END/ACCESS/GET, comma-separated combos), `function_index`, `is_exit` (bool), `ptr` (resource pointer), `ts_ns` (nanosecond timestamp).

Critical semantics:
- **WAIT event sets**: WAIT + associated events are recorded at both function entry (`is_exit=false`) and exit (`is_exit=true`) with shared timestamps within each set.
- **ACQUIRE/GET on return**: When a function returns a resource that is marked, ACQUIRE or GET is recorded only at exit (`is_exit=true`) with no corresponding entry event. Note: If a resource is in the function parameter list, the event is still recorded in the function entry.
- **END events**: Indicate thread termination. An END event shares the same `ptr` and resource type as the resource the thread was operating on when it ended. Used to confirm orphan WAIT detection (WAIT entry with no matching exit).
- **All other events** are recorded at function entry only, except the two cases above.

## Running

```bash
conda activate XXX

pip install dash plotly pandas

# With pre-loaded example data (opens browser automatically):
python app.py ./data-example

# Without pre-loaded data (load via browser UI):
python app.py
```

Dependencies: `Use conda environment by running './miniconda3/Scripts/activate' and then 'conda activate XXX'`

## Architecture

```
app.py              — Entry point, CLI args, Dash server
data_loader.py      — JSON data loading → pandas DataFrame
filters/            — Extensible global filter registry and filter modules
layouts/            — Dash layout components (main, filter panel, timeline, statistics, bottleneck)
callbacks/          — Dash callbacks for interactivity and filter application
data-example/       — Example profiling data
docs/               — Project documentation
```

## Directory Guide

Each subdirectory contains its own `CLAUDE.md` with detailed file descriptions:

- **`filters/CLAUDE.md`** — Extensible global filter package. Self-registering filter modules that pre-filter data for all tabs. Value filters (resource type/thread/function name dropdowns) live directly under `filters/`; semantic filters (complex cross-row analysis like No-USE-After-RELEASE) live under `filters/semantic/`.
- **`layouts/CLAUDE.md`** — UI layout modules defining the Dash component tree for the main page, global filter panel, and each tab (Timeline, Statistics, Bottleneck Analysis). Pure structure, no callback logic.
- **`callbacks/CLAUDE.md`** — Callback modules that register Dash callbacks for data loading, global filter application, heatmap rendering, statistics charts, and bottleneck analysis. Lists all public functions and callback I/O.
- **`data-example/CLAUDE.md`** — Example profiling dataset: mapping files, function metadata, and per-thread event traces. Includes the `dynamic-profiling-data/` subdirectory with 26 thread JSON files.
- **`docs/CLAUDE.md`** — Project documentation including the full component reference (`components.md`).

## Protocol

Every edition on any Python script's code must be reflected (i.e., updated) in:
1. The **script's own header docstring** — keep Responsibilities, Public functions, Dash IDs, and Callbacks sections accurate.
2. The **CLAUDE.md under the same directory** as the modified script — update the file's description to match the new behaviour.
3. **Check if there are any tasks required by the CLAUDE.md** — if the CLAUDE.md lists pending tasks or requirements, address them as part of the edit.

Every modification on a subdirectory's CLAUDE.md should be reflected (i.e., updated) in the CLAUDE.md in its parent directory, recursively up to this root CLAUDE.md.