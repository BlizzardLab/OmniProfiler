"""Bottleneck Analysis tab layout.

Responsibilities:
    - Resource type and thread dropdown filters.
    - Time window RangeSlider with dynamic label reflecting the current unit.
    - Time bins slider controlling temporal resolution for heatmaps.
    - Contention Scoreboard section: resource type contention bar chart,
      top contended addresses horizontal bar chart.
    - Temporal Contention Heatmap: per-thread WAIT wall-time duration for
      Sankey entities; blank until a resource type bar is clicked.
    - Cascading Contention Map: Sankey diagram showing multi-layer cascading
      address→function→thread flow. Cascade depth dropdown controls how many
      BFS layers to expand (0–3). Per-layer explore/display sliders control
      how many addresses drive BFS expansion vs. how many are displayed.
      Min Node Flow input (default 2) filters out nodes whose total flow
      count (number of incoming + outgoing links) is below the threshold.
      Reset button clears thread-pair click-highlight selection.
      Layer slider rows are shown/hidden based on the selected depth.

Public functions:
    bottleneck_layout() -> html.Div

Dash component IDs exposed:
    bottleneck-resource-dropdown, bottleneck-thread-dropdown,
    bottleneck-time-range, bottleneck-time-label,
    bottleneck-bins-slider,
    bottleneck-restype-bar, bottleneck-addr-bar,
    bottleneck-temporal-heatmap,
    bottleneck-cascade-depth,
    bottleneck-cascade-min-flow,
    bottleneck-cascade-explore-0 .. bottleneck-cascade-explore-3,
    bottleneck-cascade-display-0 .. bottleneck-cascade-display-3,
    bottleneck-cascade-row-0 .. bottleneck-cascade-row-3,
    bottleneck-cascade-sankey,
    bottleneck-cascade-reset,
    bottleneck-hover-dummy

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import dcc, html


def bottleneck_layout():
    return html.Div([
        html.H3("Bottleneck Analysis", style={"marginTop": "0"}),

        # Controls row
        html.Div([
            html.Div([
                html.Label("Resource Type", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Dropdown(id="bottleneck-resource-dropdown", placeholder="All resources",
                             style={"width": "220px"}),
            ], style={"marginRight": "20px"}),
            html.Div([
                html.Label("Thread", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Dropdown(id="bottleneck-thread-dropdown", placeholder="All threads",
                             style={"width": "220px"}),
            ], style={"marginRight": "20px"}),
            html.Div([
                html.Label("Time Bins", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Slider(
                    id="bottleneck-bins-slider",
                    min=20, max=500, step=10, value=100,
                    marks={20: "20", 100: "100", 250: "250", 500: "500"},
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
            ], style={"width": "220px"}),
        ], style={"display": "flex", "alignItems": "flex-end", "marginBottom": "12px"}),

        # Time window selector
        html.Div([
            html.Label(id="bottleneck-time-label", children="Time Window (ms, relative)",
                       style={"fontWeight": "bold", "fontSize": "13px"}),
            dcc.RangeSlider(
                id="bottleneck-time-range",
                min=0, max=1, step=0.1,
                value=[0, 1],
                marks={},
                tooltip={"placement": "bottom", "always_visible": True},
                allowCross=False,
            ),
        ], style={"marginBottom": "16px"}),

        # Section 1 — Contention Scoreboard
        html.H4("Contention Scoreboard"),

        # Two-column: resource type bar + address bar
        html.Div([
            html.Div([
                html.H5("Resource Type Contention"),
                dcc.Graph(id="bottleneck-restype-bar"),
            ], style={"flex": "1", "marginRight": "16px"}),
            html.Div([
                html.H5("Top Contended Addresses"),
                dcc.Graph(id="bottleneck-addr-bar"),
            ], style={"flex": "1"}),
        ], style={"display": "flex", "gap": "16px"}),

        # Cascading Contention Map (below the two bar charts)
        html.Div([
            html.H5("Cascading Contention Map"),
            html.P("Address → Function → Thread flow for the selected resource type. "
                   "Click a resource type bar above to populate. "
                   "Increase cascade depth to discover collateral resource types via shared functions.",
                   style={"color": "#666", "fontSize": "13px"}),

            # Cascade controls row
            html.Div([
                # Cascade depth dropdown
                html.Div([
                    html.Label("Cascade Depth", style={"fontWeight": "bold", "fontSize": "13px"}),
                    dcc.Dropdown(
                        id="bottleneck-cascade-depth",
                        options=[
                            {"label": "Layer 0 only", "value": 0},
                            {"label": "1 layer", "value": 1},
                            {"label": "2 layers", "value": 2},
                            {"label": "3 layers", "value": 3},
                        ],
                        value=0,
                        clearable=False,
                        style={"width": "160px"},
                    ),
                ], style={"marginRight": "24px"}),

                # Min node flow input + Reset button
                html.Div([
                    html.Label("Min Node Flow",
                               style={"fontWeight": "bold", "fontSize": "13px"}),
                    dcc.Input(
                        id="bottleneck-cascade-min-flow",
                        type="number", min=0, step=1, value=2,
                        style={"width": "70px"},
                    ),
                    html.Button("Reset", id="bottleneck-cascade-reset",
                                style={"marginTop": "4px", "fontSize": "12px"}),
                ], style={"marginRight": "24px"}),

                # Per-layer slider panel
                html.Div([
                    # Layer 0 sliders
                    html.Div([
                        html.Span("L0", style={"fontWeight": "bold", "fontSize": "12px",
                                               "color": "#3498db", "minWidth": "24px"}),
                        html.Span("Explore:", style={"fontSize": "12px", "marginLeft": "8px"}),
                        dcc.Slider(id="bottleneck-cascade-explore-0",
                                   min=1, max=50, step=1, value=15,
                                   tooltip={"placement": "bottom", "always_visible": False},
                                   marks=None),
                        html.Span("Display:", style={"fontSize": "12px", "marginLeft": "12px"}),
                        dcc.Slider(id="bottleneck-cascade-display-0",
                                   min=1, max=50, step=1, value=15,
                                   tooltip={"placement": "bottom", "always_visible": False},
                                   marks=None),
                    ], id="bottleneck-cascade-row-0",
                       style={"display": "flex", "alignItems": "center", "gap": "4px",
                              "marginBottom": "4px"}),
                    # Layer 1 sliders
                    html.Div([
                        html.Span("L1", style={"fontWeight": "bold", "fontSize": "12px",
                                               "color": "#e67e22", "minWidth": "24px"}),
                        html.Span("Explore:", style={"fontSize": "12px", "marginLeft": "8px"}),
                        dcc.Slider(id="bottleneck-cascade-explore-1",
                                   min=1, max=50, step=1, value=10,
                                   tooltip={"placement": "bottom", "always_visible": False},
                                   marks=None),
                        html.Span("Display:", style={"fontSize": "12px", "marginLeft": "12px"}),
                        dcc.Slider(id="bottleneck-cascade-display-1",
                                   min=1, max=50, step=1, value=10,
                                   tooltip={"placement": "bottom", "always_visible": False},
                                   marks=None),
                    ], id="bottleneck-cascade-row-1",
                       style={"display": "none", "alignItems": "center", "gap": "4px",
                              "marginBottom": "4px"}),
                    # Layer 2 sliders
                    html.Div([
                        html.Span("L2", style={"fontWeight": "bold", "fontSize": "12px",
                                               "color": "#27ae60", "minWidth": "24px"}),
                        html.Span("Explore:", style={"fontSize": "12px", "marginLeft": "8px"}),
                        dcc.Slider(id="bottleneck-cascade-explore-2",
                                   min=1, max=50, step=1, value=5,
                                   tooltip={"placement": "bottom", "always_visible": False},
                                   marks=None),
                        html.Span("Display:", style={"fontSize": "12px", "marginLeft": "12px"}),
                        dcc.Slider(id="bottleneck-cascade-display-2",
                                   min=1, max=50, step=1, value=5,
                                   tooltip={"placement": "bottom", "always_visible": False},
                                   marks=None),
                    ], id="bottleneck-cascade-row-2",
                       style={"display": "none", "alignItems": "center", "gap": "4px",
                              "marginBottom": "4px"}),
                    # Layer 3 sliders
                    html.Div([
                        html.Span("L3", style={"fontWeight": "bold", "fontSize": "12px",
                                               "color": "#8e44ad", "minWidth": "24px"}),
                        html.Span("Explore:", style={"fontSize": "12px", "marginLeft": "8px"}),
                        dcc.Slider(id="bottleneck-cascade-explore-3",
                                   min=1, max=50, step=1, value=5,
                                   tooltip={"placement": "bottom", "always_visible": False},
                                   marks=None),
                        html.Span("Display:", style={"fontSize": "12px", "marginLeft": "12px"}),
                        dcc.Slider(id="bottleneck-cascade-display-3",
                                   min=1, max=50, step=1, value=5,
                                   tooltip={"placement": "bottom", "always_visible": False},
                                   marks=None),
                    ], id="bottleneck-cascade-row-3",
                       style={"display": "none", "alignItems": "center", "gap": "4px",
                              "marginBottom": "4px"}),
                ], style={"flex": "1"}),
            ], style={"display": "flex", "alignItems": "flex-start", "marginBottom": "12px"}),

            dcc.Graph(id="bottleneck-cascade-sankey"),
            html.Div(id="bottleneck-hover-dummy", style={"display": "none"}),
        ], style={"marginTop": "16px"}),

        # Section 2 — Temporal Contention Heatmap (Sankey-driven)
        html.Div([
            html.H4("Temporal Contention Heatmap"),
            html.P("Per-thread WAIT wall-time duration for addresses and "
                   "threads in the Sankey diagram above. "
                   "Click a resource type bar to populate.",
                   style={"color": "#666", "fontSize": "13px"}),
            dcc.Graph(id="bottleneck-temporal-heatmap"),
        ], style={"marginTop": "24px"}),

    ])
