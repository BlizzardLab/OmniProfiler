"""Statistics tab layout.

Responsibilities:
    - Resource type and thread dropdown filters.
    - Event type checklist (USE / RELEASE / ACQUIRE / WAIT / ACCESS / GET).
    - Time window range slider with a dynamic label reflecting the current unit.
    - Graph containers for the resource bar chart and per-thread bar chart.
    - Container for the function hotspot DataTable.
    - WAIT Duration Flamegraph: horizontal bar chart showing WAIT intervals
      stacked by overlap layer, colored by resource type.
    - WAIT hotspot DataTable: top functions by total WAIT wall-time, with
      event count, unique addresses, threads, and resource types.

Public functions:
    statistics_layout() -> html.Div

Dash component IDs exposed:
    stats-resource-dropdown, stats-thread-dropdown, stats-event-checklist,
    stats-time-range, stats-time-label,
    stats-resource-bar, stats-function-table, stats-thread-bar,
    stats-wait-flamegraph, stats-wait-table

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import dcc, html


def statistics_layout():
    return html.Div([
        html.H3("Statistics", style={"marginTop": "0"}),

        # Filters
        html.Div([ 
            html.Div([
                html.Label("Resource Type", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Dropdown(id="stats-resource-dropdown", placeholder="All resources",
                             style={"width": "220px"}),
            ], style={"marginRight": "20px"}),
            html.Div([
                html.Label("Thread", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Dropdown(id="stats-thread-dropdown", placeholder="All threads",
                             style={"width": "220px"}),
            ], style={"marginRight": "20px"}),
            html.Div([
                html.Label("Event Types", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Checklist(
                    id="stats-event-checklist",
                    options=[
                        {"label": " USE", "value": "USE"},
                        {"label": " RELEASE", "value": "RELEASE"},
                        {"label": " ACQUIRE", "value": "ACQUIRE"},
                        {"label": " WAIT", "value": "WAIT"},
                        {"label": " ACCESS", "value": "ACCESS"},
                        {"label": " GET", "value": "GET"},
                    ],
                    value=["USE", "RELEASE", "ACQUIRE", "WAIT", "ACCESS", "GET"],
                    inline=True,
                    style={"fontSize": "13px"},
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"marginRight": "12px"},
                ),
            ]),
        ], style={"display": "flex", "alignItems": "flex-end", "marginBottom": "12px"}),

        # Time window selector
        html.Div([
            html.Label(id="stats-time-label", children="Time Window (ms, relative)",
                       style={"fontWeight": "bold", "fontSize": "13px"}),
            dcc.RangeSlider(
                id="stats-time-range",
                min=0, max=1, step=0.1,
                value=[0, 1],
                marks={},
                tooltip={"placement": "bottom", "always_visible": True},
                allowCross=False,
            ),
        ], style={"marginBottom": "16px"}),

        # Resource usage chart
        html.Div([
            html.H4("Event Counts by Resource Type"),
            dcc.Graph(id="stats-resource-bar"),
        ]),

        # Two-column layout
        html.Div([
            # Function hotspots
            html.Div([
                html.H4("Top Functions by Event Count"),
                html.Div(id="stats-function-table"),
            ], style={"flex": "1", "marginRight": "16px"}),

            # Per-thread summary
            html.Div([
                html.H4("Events per Thread"),
                dcc.Graph(id="stats-thread-bar"),
            ], style={"flex": "1"}),
        ], style={"display": "flex", "gap": "16px"}),

        # WAIT Duration Flamegraph
        html.Div([
            html.H4("WAIT Duration Flamegraph"),
            dcc.Graph(id="stats-wait-flamegraph"),
        ], style={"marginTop": "24px"}),

        # WAIT hotspot table
        html.Div(id="stats-wait-table", style={"marginTop": "16px"}),
    ])
