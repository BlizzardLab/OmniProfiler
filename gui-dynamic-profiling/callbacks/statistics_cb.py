"""Statistics tab callbacks.

Responsibilities:
    - Populate resource type and thread filter dropdowns.
    - Configure the time window RangeSlider (min/max/step/marks) based on
      loaded data and the current time unit.
    - Render a grouped bar chart of event counts by resource type.
    - Render a function hotspot DataTable (top 30 by event count) with
      unique address count, thread count, and resource types with their
      operation types.
    - Render a horizontal bar chart of events per thread with ascending
      thread index order.
    - Render a WAIT Duration Flamegraph: pairs WAIT entry/exit events using
      backward analysis (descending timestamp) to handle ringbuffer cutoff,
      assigns overlapping intervals to stacked layers via greedy sweep-line,
      and draws horizontal bars colored by resource type.
    - Render a WAIT hotspot DataTable (top 30 by total wall-time) with
      pair count, unique addresses, thread count, and resource types with
      co-occurring operations.
    - All charts honour the event type checklist, time window filter, and
      time unit toggle.
    - Use globally filtered data from get_filtered_df() and re-fire when
      filtered-data-version changes.

Public functions:
    register_statistics_callbacks(app) -> None

Dash callbacks registered (5):
    update_dropdowns      — Input: data-store, time-unit-toggle;
                             Output: stats-resource-dropdown, stats-thread-dropdown,
                             stats-time-range (min/max/value/step/marks),
                             stats-time-label
    update_resource_bar   — Input: data-store, stats-thread-dropdown,
                             stats-event-checklist, stats-time-range,
                             time-unit-toggle, filtered-data-version;
                             Output: stats-resource-bar figure
    update_function_table — Input: data-store, stats-resource-dropdown,
                             stats-thread-dropdown, stats-event-checklist,
                             stats-time-range, time-unit-toggle,
                             filtered-data-version;
                             Output: stats-function-table children
    update_thread_bar     — Input: data-store, stats-resource-dropdown,
                             stats-event-checklist, stats-time-range,
                             time-unit-toggle, filtered-data-version;
                             Output: stats-thread-bar figure
    update_wait_flamegraph — Input: data-store, stats-resource-dropdown,
                             stats-thread-dropdown, stats-event-checklist,
                             stats-time-range, time-unit-toggle,
                             filtered-data-version;
                             Output: stats-wait-flamegraph figure,
                             stats-wait-table children

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, callback, html, dash_table

from callbacks.data_callbacks import get_cached_dataset
from filters import get_filtered_df


def _time_divisor(unit):
    return 1e9 if unit == "s" else 1e6


def _time_label(unit):
    return "s" if unit == "s" else "ms"


def _apply_time_filter(df, time_range, time_unit):
    """Filter df to the selected time window."""
    if time_range and len(time_range) == 2:
        divisor = _time_divisor(time_unit)
        t_lo, t_hi = time_range
        ts = df["ts_relative_ns"] / divisor
        df = df[(ts >= t_lo) & (ts <= t_hi)]
    return df


_ALL_EVENT_TYPES = ["USE", "RELEASE", "ACQUIRE", "WAIT", "ACCESS", "GET"]


def _apply_event_filter(df, event_types):
    """Keep only rows that match at least one of the selected event types."""
    if not event_types:
        return df.iloc[0:0]
    combined_mask = False
    for et in event_types:
        combined_mask = combined_mask | df[f"has_{et.lower()}"]
    return df[combined_mask]


def _assign_layers(intervals):
    """Assign each interval to the lowest non-overlapping layer.

    Args:
        intervals: list of dicts with 'start' and 'end' keys (plus metadata).
    Returns:
        The same list with an added 'layer' key on each dict.
    """
    sorted_ivs = sorted(intervals, key=lambda x: x["start"])
    layer_ends = []  # end time of last interval in each layer
    for iv in sorted_ivs:
        placed = False
        for i, end in enumerate(layer_ends):
            if iv["start"] >= end:
                layer_ends[i] = iv["end"]
                iv["layer"] = i
                placed = True
                break
        if not placed:
            iv["layer"] = len(layer_ends)
            layer_ends.append(iv["end"])
    return sorted_ivs


def register_statistics_callbacks(app):
    @app.callback(
        Output("stats-resource-dropdown", "options"),
        Output("stats-thread-dropdown", "options"),
        Output("stats-time-range", "min"),
        Output("stats-time-range", "max"),
        Output("stats-time-range", "value"),
        Output("stats-time-range", "step"),
        Output("stats-time-range", "marks"),
        Output("stats-time-label", "children"),
        Input("data-store", "data"),
        Input("time-unit-toggle", "value"),
    )
    def update_dropdowns(store_data, time_unit):
        tlabel = _time_label(time_unit)
        if not store_data or not store_data.get("loaded"):
            return [], [], 0, 1, [0, 1], 0.1, {}, f"Time Window ({tlabel}, relative)"
        resources = [{"label": r, "value": r} for r in sorted(store_data["resource_types"])]
        threads = [{"label": t, "value": t} for t in store_data["thread_labels"]]

        divisor = _time_divisor(time_unit)
        duration = (store_data["time_range_ns"][1] - store_data["time_range_ns"][0]) / divisor
        duration_r = round(duration, 4)
        step = max(0.0001, round(duration / 1000, 4))
        marks = {
            0: "0",
            duration_r: f"{duration_r:.4g}",
        }
        return (resources, threads, 0, duration_r, [0, duration_r], step, marks,
                f"Time Window ({tlabel}, relative)")

    @app.callback(
        Output("stats-resource-bar", "figure"),
        Input("data-store", "data"),
        Input("stats-thread-dropdown", "value"),
        Input("stats-event-checklist", "value"),
        Input("stats-time-range", "value"),
        Input("time-unit-toggle", "value"),
        Input("filtered-data-version", "data"),
    )
    def update_resource_bar(store_data, thread_filter, event_types, time_range, time_unit, _fv):
        if not store_data or not store_data.get("loaded"):
            return _empty_fig("Load data to see statistics")

        df = get_filtered_df()
        if df is None:
            dataset = get_cached_dataset()
            if not dataset:
                return _empty_fig("No data in cache")
            df = dataset["df"]
        df = _apply_time_filter(df, time_range, time_unit)
        if thread_filter:
            df = df[df["thread_label"] == thread_filter]
        df = _apply_event_filter(df, event_types)

        if len(df) == 0:
            return _empty_fig("No events match filters")

        # Count events by resource type and event kind
        selected = event_types or []
        rows = []
        for rt in sorted(df["resource_type"].unique()):
            rt_df = df[df["resource_type"] == rt]
            for et in selected:
                count = rt_df[f"has_{et.lower()}"].sum()
                if count > 0:
                    rows.append({"resource_type": rt, "event_type": et, "count": int(count)})

        if not rows:
            return _empty_fig("No events")

        import pandas as pd
        bar_df = pd.DataFrame(rows)
        fig = px.bar(bar_df, x="resource_type", y="count", color="event_type",
                     barmode="group", labels={"resource_type": "Resource Type", "count": "Event Count"},
                     color_discrete_map={"USE": "#3498db", "RELEASE": "#2ecc71",
                                         "ACQUIRE": "#e67e22", "WAIT": "#e74c3c",
                                         "ACCESS": "#9b59b6", "GET": "#1abc9c"})
        fig.update_layout(margin=dict(l=40, r=20, t=20, b=40), legend_title_text="Event Type")
        return fig

    @app.callback(
        Output("stats-function-table", "children"),
        Input("data-store", "data"),
        Input("stats-resource-dropdown", "value"),
        Input("stats-thread-dropdown", "value"),
        Input("stats-event-checklist", "value"),
        Input("stats-time-range", "value"),
        Input("time-unit-toggle", "value"),
        Input("filtered-data-version", "data"),
    )
    def update_function_table(store_data, resource_filter, thread_filter, event_types, time_range, time_unit, _fv):
        if not store_data or not store_data.get("loaded"):
            return html.P("No data loaded.", style={"color": "#888"})

        df = get_filtered_df()
        if df is None:
            dataset = get_cached_dataset()
            if not dataset:
                return ""
            df = dataset["df"]
        df = _apply_time_filter(df, time_range, time_unit)
        if resource_filter:
            df = df[df["resource_type"] == resource_filter]
        if thread_filter:
            df = df[df["thread_label"] == thread_filter]
        df = _apply_event_filter(df, event_types)

        if len(df) == 0:
            return html.P("No events match filters.", style={"color": "#888"})

        # Top 30 functions by event count
        func_counts = df.groupby("function_name").agg(
            total=("function_name", "size"),
            unique_addr=("ptr", "nunique"),
            threads=("thread_label", "nunique"),
        ).sort_values("total", ascending=False).head(30).reset_index()

        # Build resource types + operations column for each top function
        selected = [ec.lower() for ec in (event_types or [])]
        top_funcs = func_counts["function_name"].values
        top_df = df[df["function_name"].isin(top_funcs)]
        res_op_map = {}
        for fn, grp in top_df.groupby("function_name"):
            parts = []
            for rt, rt_grp in grp.groupby("resource_type"):
                ops = [ec.upper() for ec in selected if rt_grp[f"has_{ec}"].any()]
                if ops:
                    parts.append(f"{rt} ({', '.join(ops)})")
            res_op_map[fn] = "; ".join(parts)
        func_counts["resources"] = func_counts["function_name"].map(res_op_map)

        return dash_table.DataTable(
            columns=[
                {"name": "Function", "id": "function_name"},
                {"name": "Events", "id": "total"},
                {"name": "Unique Addresses", "id": "unique_addr"},
                {"name": "Threads", "id": "threads"},
                {"name": "Resource Types (Operations)", "id": "resources"},
            ],
            data=func_counts.to_dict("records"),
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "4px 8px", "fontSize": "12px"},
            style_header={"fontWeight": "bold", "backgroundColor": "#f0f0f0"},
            style_cell_conditional=[
                {"if": {"column_id": "resources"},
                 "maxWidth": "400px", "whiteSpace": "normal"},
            ],
            sort_action="native",
            page_size=15,
        )

    @app.callback(
        Output("stats-thread-bar", "figure"),
        Input("data-store", "data"),
        Input("stats-resource-dropdown", "value"),
        Input("stats-event-checklist", "value"),
        Input("stats-time-range", "value"),
        Input("time-unit-toggle", "value"),
        Input("filtered-data-version", "data"),
    )
    def update_thread_bar(store_data, resource_filter, event_types, time_range, time_unit, _fv):
        if not store_data or not store_data.get("loaded"):
            return _empty_fig("Load data to see thread statistics")

        df = get_filtered_df()
        if df is None:
            dataset = get_cached_dataset()
            if not dataset:
                return _empty_fig("No data in cache")
            df = dataset["df"]
        df = _apply_time_filter(df, time_range, time_unit)
        if resource_filter:
            df = df[df["resource_type"] == resource_filter]
        df = _apply_event_filter(df, event_types)

        if len(df) == 0:
            return _empty_fig("No events match filters")

        # Sort by thread index ascending
        thread_counts = df.groupby("thread_label").size()
        sorted_labels = sorted(thread_counts.index, key=int)
        thread_counts = thread_counts.reindex(sorted_labels)

        fig = go.Figure(go.Bar(
            x=thread_counts.values,
            y=thread_counts.index.tolist(),
            orientation="h",
            marker_color="#3498db",
        ))
        fig.update_layout(
            xaxis_title="Event Count",
            yaxis_title="Thread",
            margin=dict(l=60, r=20, t=20, b=40),
            yaxis=dict(type="category", categoryorder="array",
                       categoryarray=sorted_labels),
        )
        return fig

    @app.callback(
        Output("stats-wait-flamegraph", "figure"),
        Output("stats-wait-table", "children"),
        Input("data-store", "data"),
        Input("stats-resource-dropdown", "value"),
        Input("stats-thread-dropdown", "value"),
        Input("stats-event-checklist", "value"),
        Input("stats-time-range", "value"),
        Input("time-unit-toggle", "value"),
        Input("filtered-data-version", "data"),
    )
    def update_wait_flamegraph(store_data, resource_filter, thread_filter,
                               event_types, time_range, time_unit, _fv):
        empty_table = html.P("No WAIT data.", style={"color": "#888"})
        if not store_data or not store_data.get("loaded"):
            return _empty_fig("Load data to see WAIT flamegraph"), empty_table
        if not event_types or "WAIT" not in event_types:
            return _empty_fig("WAIT not selected in event types"), empty_table

        df = get_filtered_df()
        if df is None:
            dataset = get_cached_dataset()
            if not dataset:
                return _empty_fig("No data in cache"), empty_table
            df = dataset["df"]
        df = _apply_time_filter(df, time_range, time_unit)
        if resource_filter:
            df = df[df["resource_type"] == resource_filter]
        if thread_filter:
            df = df[df["thread_label"] == thread_filter]

        wait_df = df[df["has_wait"]].copy()

        # Filter by event type checklist: keep a WAIT event if it is pure WAIT
        # (no co-occurring types) or at least one of its co-occurring non-WAIT
        # types is still selected.  E.g. unchecking ACCESS removes "WAIT,ACCESS"
        # but keeps "WAIT,ACCESS,ACQUIRE" when ACQUIRE is checked.
        _non_wait = ["USE", "RELEASE", "ACQUIRE", "ACCESS", "GET"]
        selected_non_wait = [et for et in _non_wait if et in event_types]
        if len(selected_non_wait) < len(_non_wait):
            has_any = False
            for et in _non_wait:
                has_any = has_any | wait_df[f"has_{et.lower()}"]
            has_selected = False
            for et in selected_non_wait:
                has_selected = has_selected | wait_df[f"has_{et.lower()}"]
            wait_df = wait_df[~has_any | has_selected]

        if len(wait_df) == 0:
            return _empty_fig("No WAIT events match filters"), empty_table

        # Per-thread final timestamps for orphan WAIT handling
        thread_final_ts = df.groupby("thread_id")["ts_relative_ns"].max()
        # Use END events if available
        has_end_col = "has_end" in df.columns
        if has_end_col and df["has_end"].any():
            end_ts = df[df["has_end"]].groupby("thread_id")["ts_relative_ns"].max()
            thread_final_ts = thread_final_ts.combine(end_ts, max, fill_value=0)

        # Pair entry/exit WAIT events by (thread_id, function_index, ptr).
        # Analyze backward (descending timestamp) to handle ringbuffer cutoff:
        # pre-trace exits (from truncated ringbuffers) sit at the chronological
        # start and are naturally left over as unmatched after backward iteration.
        intervals = []
        grouped = wait_df.groupby(["thread_id", "function_index", "ptr"])
        for (tid, func_idx, ptr), group in grouped:
            events = group.sort_values(["ts_relative_ns", "is_exit"],
                                       ascending=[False, False])
            pending_exits = []
            for _, ev in events.iterrows():
                if ev["is_exit"]:
                    pending_exits.append(ev)
                else:
                    if pending_exits:
                        exit_ev = pending_exits.pop()  # LIFO: match nearest exit
                        start = ev["ts_relative_ns"]
                        end = exit_ev["ts_relative_ns"]
                        if end > start:
                            intervals.append({
                                "start": start,
                                "end": end,
                                "resource_type": ev["resource_type"],
                                "function_name": ev["function_name"],
                                "thread_label": ev["thread_label"],
                                "thread_id": tid,
                                "ptr": ptr,
                                "orphan": False,
                            })
                    else:
                        # Entry with no subsequent exit — orphan WAIT
                        # (thread aborted while function still running)
                        start = ev["ts_relative_ns"]
                        final_ts = thread_final_ts.get(tid, start)
                        if final_ts > start:
                            intervals.append({
                                "start": start,
                                "end": final_ts,
                                "resource_type": ev["resource_type"],
                                "function_name": ev["function_name"],
                                "thread_label": ev["thread_label"],
                                "thread_id": tid,
                                "ptr": ptr,
                                "orphan": True,
                            })
            # Remaining pending_exits are pre-trace exits (ringbuffer cutoff) — discard

        if not intervals:
            return _empty_fig("No WAIT entry/exit pairs found"), empty_table

        # Assign layers using greedy interval packing
        intervals = _assign_layers(intervals)

        # Build figure with one trace per resource type
        divisor = _time_divisor(time_unit)
        tlabel = _time_label(time_unit)
        resource_types = sorted(set(iv["resource_type"] for iv in intervals))

        # Color palette for resource types
        palette = ["#e74c3c", "#c0392b", "#e67e22", "#d35400",
                   "#f39c12", "#8e44ad", "#2980b9", "#16a085"]
        color_map = {rt: palette[i % len(palette)] for i, rt in enumerate(resource_types)}

        fig = go.Figure()
        for rt in resource_types:
            rt_ivs = [iv for iv in intervals if iv["resource_type"] == rt]
            starts = [iv["start"] / divisor for iv in rt_ivs]
            durations = [(iv["end"] - iv["start"]) / divisor for iv in rt_ivs]
            layers = [f"Layer {iv['layer']}" for iv in rt_ivs]
            hover_texts = [
                f"<b>{iv['function_name']}</b><br>"
                f"Thread: {iv['thread_label']}<br>"
                f"Resource: {iv['resource_type']}<br>"
                f"Duration: {(iv['end'] - iv['start']) / divisor:.4g} {tlabel}"
                f"{'<br><i>(orphan — extended to thread end)</i>' if iv['orphan'] else ''}"
                for iv in rt_ivs
            ]

            fig.add_trace(go.Bar(
                base=starts,
                x=durations,
                y=layers,
                orientation="h",
                name=rt,
                marker_color=color_map[rt],
                marker_line=dict(
                    color=["#ff0" if iv["orphan"] else color_map[rt] for iv in rt_ivs],
                    width=[2 if iv["orphan"] else 0 for iv in rt_ivs],
                ),
                hovertext=hover_texts,
                hoverinfo="text",
            ))

        max_layer = max(iv["layer"] for iv in intervals)
        layer_labels = [f"Layer {i}" for i in range(max_layer + 1)]
        fig.update_layout(
            barmode="overlay",
            xaxis_title=f"Time ({tlabel}, relative)",
            yaxis_title="Overlap Layer",
            yaxis=dict(type="category", categoryorder="array",
                       categoryarray=layer_labels),
            margin=dict(l=60, r=20, t=20, b=40),
            legend_title_text="Resource Type",
        )
        return fig, _build_wait_table(intervals, wait_df, divisor, tlabel)


def _build_wait_table(intervals, wait_df, divisor, tlabel):
    """Build a top-k WAIT hotspot DataTable from paired intervals.

    Aggregates by function_name: total wall-time, pair count, unique
    addresses, thread count, and resource types with co-occurring operations.
    """
    import pandas as pd

    rows = []
    for iv in intervals:
        rows.append({
            "function_name": iv["function_name"],
            "duration_ns": iv["end"] - iv["start"],
            "ptr": iv["ptr"],
            "thread_label": iv["thread_label"],
            "resource_type": iv["resource_type"],
        })
    iv_df = pd.DataFrame(rows)

    agg = iv_df.groupby("function_name").agg(
        total_duration_ns=("duration_ns", "sum"),
        event_count=("duration_ns", "size"),
        unique_addr=("ptr", "nunique"),
        threads=("thread_label", "nunique"),
    ).sort_values("total_duration_ns", ascending=False).head(30).reset_index()

    agg[f"Total Duration ({tlabel})"] = (agg["total_duration_ns"] / divisor).round(6)
    agg = agg.drop(columns=["total_duration_ns"])

    # Build resource type + co-occurring operations column from original wait_df
    _event_cols = ["has_use", "has_release", "has_acquire", "has_access", "has_get"]
    _event_labels = ["USE", "RELEASE", "ACQUIRE", "ACCESS", "GET"]
    top_funcs = agg["function_name"].values
    top_wait = wait_df[wait_df["function_name"].isin(top_funcs)]
    res_op_map = {}
    for fn, grp in top_wait.groupby("function_name"):
        parts = []
        for rt, rt_grp in grp.groupby("resource_type"):
            ops = ["WAIT"]
            for col, label in zip(_event_cols, _event_labels):
                if col in rt_grp.columns and rt_grp[col].any():
                    ops.append(label)
            parts.append(f"{rt} ({', '.join(ops)})")
        res_op_map[fn] = "; ".join(parts)
    agg["resources"] = agg["function_name"].map(res_op_map)

    return html.Div([
        html.H4("Top Functions by WAIT Wall-Time"),
        dash_table.DataTable(
            columns=[
                {"name": "Function", "id": "function_name"},
                {"name": f"Total Duration ({tlabel})", "id": f"Total Duration ({tlabel})"},
                {"name": "WAIT Pairs", "id": "event_count"},
                {"name": "Unique Addresses", "id": "unique_addr"},
                {"name": "Threads", "id": "threads"},
                {"name": "Resource Types (Operations)", "id": "resources"},
            ],
            data=agg.to_dict("records"),
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "4px 8px", "fontSize": "12px"},
            style_header={"fontWeight": "bold", "backgroundColor": "#f0f0f0"},
            style_cell_conditional=[
                {"if": {"column_id": "resources"},
                 "maxWidth": "400px", "whiteSpace": "normal"},
            ],
            sort_action="native",
            page_size=15,
        ),
    ])


def _empty_fig(message="No data"):
    fig = go.Figure()
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(text=message, xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=16, color="#888"))],
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig
