"""Data loading and caching callbacks.

Responsibilities:
    - Load profiling data from a directory via the Load button or CLI pre-load.
    - Cache the full dataset (DataFrame + mappings) at module level to avoid
      serializing large objects through dcc.Store.
    - Produce a lightweight JSON-serializable summary for dcc.Store consumers.
    - Render the summary banner with thread/event counts and duration, updating
      dynamically when the time unit toggle changes.

Public functions:
    get_cached_dataset() -> dict
    set_cached_dataset(dataset) -> None
    preload_data(directory_path) -> dict
    register_data_callbacks(app, initial_store_data) -> None

Dash callbacks registered (2):
    load_data       — Input: load-btn; Output: data-store, loading-target
    update_summary  — Input: data-store, time-unit-toggle; Output: summary-banner

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

import json

from dash import Input, Output, State, callback, html

from data_loader import load_dataset

# Module-level cache for the loaded dataset
_cached_dataset = {}


def get_cached_dataset():
    return _cached_dataset


def set_cached_dataset(dataset):
    global _cached_dataset
    _cached_dataset = dataset


def preload_data(directory_path: str):
    """Pre-load data from CLI argument."""
    dataset = load_dataset(directory_path)
    set_cached_dataset(dataset)
    return _make_store_data(dataset, directory_path)


def _make_store_data(dataset, directory_path):
    """Create a JSON-serializable summary to store in dcc.Store."""
    df = dataset["df"]
    return {
        "loaded": True,
        "directory": directory_path,
        "num_threads": len(dataset["threads"]),
        "num_events": len(df),
        "resource_types": list(dataset["resource_map"].keys()),
        "threads": [f"{p}_{t}" for p, t in dataset["threads"]],
        "thread_labels": sorted(df["thread_label"].unique().tolist(), key=int) if len(df) > 0 else [],
        "time_range_ns": list(dataset["time_range_ns"]),
        "time_range_ms": [
            dataset["time_range_ns"][0] / 1e6,
            dataset["time_range_ns"][1] / 1e6,
        ],
        "duration_ms": (dataset["time_range_ns"][1] - dataset["time_range_ns"][0]) / 1e6,
        "event_types": sorted(df["event"].unique().tolist()) if len(df) > 0 else [],
    }


def register_data_callbacks(app, initial_store_data=None):
    @app.callback(
        Output("data-store", "data"),
        Output("loading-target", "children"),
        Input("load-btn", "n_clicks"),
        State("data-dir-input", "value"),
        prevent_initial_call=False,
    )
    def load_data(n_clicks, dir_path):
        # On initial load, use pre-loaded data if available
        if n_clicks == 0 and initial_store_data:
            return initial_store_data, ""

        if not dir_path:
            return {"loaded": False}, ""

        try:
            dataset = load_dataset(dir_path)
            set_cached_dataset(dataset)
            return _make_store_data(dataset, dir_path), ""
        except Exception as e:
            return {"loaded": False, "error": str(e)}, ""

    @app.callback(
        Output("summary-banner", "children"),
        Input("data-store", "data"),
        Input("time-unit-toggle", "value"),
    )
    def update_summary(store_data, time_unit):
        if not store_data or not store_data.get("loaded"):
            error = store_data.get("error", "") if store_data else ""
            if error:
                return html.Span(f"Error loading data: {error}", style={"color": "#e74c3c"})
            return "No data loaded. Enter a directory path above and click Load."

        duration_ns = store_data["time_range_ns"][1] - store_data["time_range_ns"][0]
        if time_unit == "s":
            duration_str = f"{duration_ns / 1e9:.3f} s"
        else:
            duration_str = f"{duration_ns / 1e6:.1f} ms"

        return html.Span([
            html.Strong(f"{store_data['num_threads']} threads"),
            f" | {store_data['num_events']:,} events",
            f" | {len(store_data['resource_types'])} resource types",
            f" | Duration: {duration_str}",
            f" | Dir: {store_data['directory']}",
        ])
