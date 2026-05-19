"""Timeline heatmap callbacks.

Responsibilities:
    - Populate the resource type dropdown from loaded data.
    - Render per-event-type heatmap subplots (USE, RELEASE, ACQUIRE, WAIT,
      ACCESS, GET)
      using vectorized NumPy binning for performance.
    - Each event appears in every subplot whose category it contains
      (e.g. "RELEASE, USE" appears in both USE and RELEASE subplots).
    - Show a detail DataTable when a heatmap cell is clicked, filtered to
      the specific event type subplot that was clicked (via customdata).
    - Respect the global time unit toggle (ms / s).
    - Use globally filtered data from get_filtered_df() and re-fire when
      filtered-data-version changes.

Public functions:
    register_timeline_callbacks(app) -> None

Dash callbacks registered (3):
    update_resource_options — Input: data-store;
                              Output: timeline-resource-dropdown options
    update_heatmap         — Input: data-store, timeline-resource-dropdown,
                              timeline-event-checklist, timeline-bins-slider,
                              time-unit-toggle, filtered-data-version;
                              Output: timeline-heatmap figure
    show_detail            — Input: timeline-heatmap clickData;
                              Output: timeline-detail children

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Input, Output, State, callback, html, dash_table

from callbacks.data_callbacks import get_cached_dataset
from filters import get_filtered_df

_CATEGORY_ORDER = ["USE", "RELEASE", "ACQUIRE", "WAIT", "ACCESS", "GET"]

_CATEGORY_COLORSCALE = {
    "USE":     [[0, "#ffffff"], [1, "#3498db"]],
    "RELEASE": [[0, "#ffffff"], [1, "#2ecc71"]],
    "ACQUIRE": [[0, "#ffffff"], [1, "#e67e22"]],
    "WAIT":    [[0, "#ffffff"], [1, "#e74c3c"]],
    "ACCESS":  [[0, "#ffffff"], [1, "#9b59b6"]],
	"GET":     [[0, "#ffffff"], [1, "#1abc9c"]],
}


def _time_divisor(unit):
    return 1e9 if unit == "s" else 1e6


def _time_label(unit):
    return "s" if unit == "s" else "ms"



def register_timeline_callbacks(app):
    @app.callback(
        Output("timeline-resource-dropdown", "options"),
        Input("data-store", "data"),
    )
    def update_resource_options(store_data):
        if not store_data or not store_data.get("loaded"):
            return []
        return [{"label": r, "value": r} for r in sorted(store_data["resource_types"])]

    @app.callback(
        Output("timeline-heatmap", "figure"),
        Input("data-store", "data"),
        Input("timeline-resource-dropdown", "value"),
        Input("timeline-event-checklist", "value"),
        Input("timeline-bins-slider", "value"),
        Input("time-unit-toggle", "value"),
        Input("filtered-data-version", "data"),
    )
    def update_heatmap(store_data, resource_type, event_types, n_bins, time_unit, _fv):
        if not store_data or not store_data.get("loaded"):
            return _empty_fig("Load data to see the timeline heatmap")

        df = get_filtered_df()
        if df is None:
            dataset = get_cached_dataset()
            if not dataset:
                return _empty_fig("No data in cache")
            df = dataset["df"]

        if not event_types:
            return _empty_fig("No event types selected")

        # Filter by resource type
        if resource_type:
            df = df[df["resource_type"] == resource_type]

        if len(df) == 0:
            return _empty_fig("No events match the current filters")

        # Keep only events that contain at least one of the selected types
        combined_mask = False
        for et in event_types:
            combined_mask = combined_mask | df[f"has_{et.lower()}"]
        df = df[combined_mask]

        if len(df) == 0:
            return _empty_fig("No events match the current filters")

        # Shared axes
        divisor = _time_divisor(time_unit)
        tlabel = _time_label(time_unit)
        ts = df["ts_relative_ns"].values / divisor
        thread_labels = sorted(df["thread_label"].unique(), key=int)
        thread_to_idx = {t: i for i, t in enumerate(thread_labels)}
        n_threads = len(thread_labels)

        t_min, t_max = ts.min(), ts.max()
        if t_max == t_min:
            t_max = t_min + 1

        bin_edges = np.linspace(t_min, t_max, n_bins + 1)
        bin_centers = np.round((bin_edges[:-1] + bin_edges[1:]) / 2, 4)

        # Precompute shared arrays
        thread_indices = df["thread_label"].map(thread_to_idx).values.astype(int)
        bin_indices = np.clip(
            ((ts - t_min) / (t_max - t_min) * n_bins).astype(int),
            0, n_bins - 1,
        )

        # One subplot per selected event type, in stable order
        active_types = [t for t in _CATEGORY_ORDER if t in event_types]
        n_types = len(active_types)

        fig = make_subplots(
            rows=n_types, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            subplot_titles=active_types,
        )

        for i, cat in enumerate(active_types):
            cat_mask = df[f"has_{cat.lower()}"].values
            heatmap = np.zeros((n_threads, n_bins), dtype=int)

            if cat_mask.any():
                np.add.at(heatmap, (thread_indices[cat_mask], bin_indices[cat_mask]), 1)

            row = i + 1
            fig.add_trace(
                go.Heatmap(
                    z=heatmap,
                    x=bin_centers,
                    y=thread_labels,
                    colorscale=_CATEGORY_COLORSCALE[cat],
                    showscale=True,
                    colorbar=dict(title=cat, len=0.85 / n_types, y=1 - (i + 0.5) / n_types),
                    customdata=np.full_like(heatmap, cat, dtype=object),
                    hovertemplate=(
                        f"<b>{cat}</b><br>"
                        f"Time: %{{x:.4f}} {tlabel}<br>"
                        "Thread: %{y}<br>"
                        "Events: %{z}<extra></extra>"
                    ),
                ),
                row=row, col=1,
            )
            fig.update_yaxes(type="category", categoryorder="array",
                             categoryarray=thread_labels, row=row, col=1)

        fig.update_xaxes(title_text=f"Time ({tlabel}, relative)", row=n_types, col=1)
        height = max(300, 180 * n_types)
        fig.update_layout(
            margin=dict(l=80, r=80, t=40, b=50),
            height=height,
        )
        return fig

    @app.callback(
        Output("timeline-detail", "children"),
        Input("timeline-heatmap", "clickData"),
        State("data-store", "data"),
        State("timeline-resource-dropdown", "value"),
        State("timeline-event-checklist", "value"),
        State("timeline-bins-slider", "value"),
        State("time-unit-toggle", "value"),
    )
    def show_detail(click_data, store_data, resource_type, event_types, n_bins, time_unit):
        if not click_data or not store_data or not store_data.get("loaded"):
            return ""

        df = get_filtered_df()
        if df is None:
            dataset = get_cached_dataset()
            if not dataset:
                return ""
            df = dataset["df"]

        # Apply same filters as heatmap
        if resource_type:
            df = df[df["resource_type"] == resource_type]
        if event_types:
            combined_mask = False
            for et in event_types:
                combined_mask = combined_mask | df[f"has_{et.lower()}"]
            df = df[combined_mask]

        if len(df) == 0:
            return html.P("No events in this cell.", style={"color": "#888"})

        divisor = _time_divisor(time_unit)
        tlabel = _time_label(time_unit)

        point = click_data["points"][0]
        thread_label = str(point["y"])
        time_val = point["x"]
        clicked_event_type = point.get("customdata")

        # Determine the bin width
        ts = df["ts_relative_ns"] / divisor
        t_min, t_max = ts.min(), ts.max()
        if t_max == t_min:
            t_max = t_min + 1
        bin_width = (t_max - t_min) / n_bins

        # Filter events in this cell
        mask = (
            (df["thread_label"] == thread_label)
            & (ts >= time_val - bin_width / 2)
            & (ts < time_val + bin_width / 2)
        )

        # Filter by the clicked event type subplot
        if clicked_event_type and f"has_{clicked_event_type.lower()}" in df.columns:
            mask = mask & df[f"has_{clicked_event_type.lower()}"]

        detail_df = df[mask].head(200)

        if len(detail_df) == 0:
            return html.P("No events in this cell.", style={"color": "#888"})

        rows = detail_df[["event", "function_name", "resource_type", "ptr", "is_exit", "ts_relative_ns"]].copy()
        rows[f"time ({tlabel})"] = (rows["ts_relative_ns"] / divisor).round(6)
        rows = rows.drop(columns=["ts_relative_ns"])

        type_label = f" [{clicked_event_type}]" if clicked_event_type else ""
        return html.Div([
            html.H4(f"Events{type_label} for thread {thread_label} at ~{time_val:.4f} {tlabel} ({len(detail_df)} events, showing up to 200)"),
            dash_table.DataTable(
                columns=[{"name": c, "id": c} for c in rows.columns],
                data=rows.to_dict("records"),
                style_table={"overflowX": "auto"},
                style_cell={"textAlign": "left", "padding": "4px 8px", "fontSize": "12px"},
                style_header={"fontWeight": "bold", "backgroundColor": "#f0f0f0"},
                page_size=50,
            ),
        ], style={
            "padding": "8px",
            "border": "1px solid #ddd",
            "borderRadius": "6px",
            "backgroundColor": "#fafafa",
        })


def _empty_fig(message="No data"):
    fig = go.Figure()
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(text=message, xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=16, color="#888"))],
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig
