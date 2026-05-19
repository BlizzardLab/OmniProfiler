"""Top-level page layout — header, summary banner, filter panel, and tab navigation.

Responsibilities:
    - Header bar with data directory text input and Load button.
    - Summary banner displaying dataset metadata and a time unit toggle (ms/s).
    - Global filter panel (from layouts.filter_panel) between summary and tabs.
    - dcc.Store for the loaded dataset summary, initial data directory, and
      filtered-data-version (incremented when global filters change).
    - Loading spinner indicator.
    - Tab container (Timeline Heatmap, Statistics, Bottleneck Analysis).

Public functions:
    make_layout(initial_data_dir) -> html.Div

Dash component IDs exposed:
    data-store, initial-data-dir, filtered-data-version, data-dir-input,
    load-btn, summary-banner, time-unit-toggle, loading-indicator,
    loading-target, filter-panel, main-tabs, tab-content

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import dcc, html

from layouts.filter_panel import filter_panel_layout


def make_layout(initial_data_dir: str = ""):
    """Build the top-level app layout."""
    return html.Div([
        # Data store (holds the loaded dataset as JSON-serializable summary)
        dcc.Store(id="data-store", storage_type="memory"),
        dcc.Store(id="initial-data-dir", data=initial_data_dir),
        dcc.Store(id="filtered-data-version", data=0),

        # Header
        html.Div([
            html.H1("Dynamic Profiling Explorer", style={"margin": "0", "fontSize": "24px"}),
            html.Div([
                dcc.Input(
                    id="data-dir-input",
                    type="text",
                    placeholder="Enter data directory path...",
                    value=initial_data_dir,
                    style={"width": "500px", "padding": "6px 10px", "fontSize": "14px"},
                ),
                html.Button("Load", id="load-btn", n_clicks=0,
                            style={"marginLeft": "8px", "padding": "6px 16px", "fontSize": "14px",
                                   "cursor": "pointer"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={
            "display": "flex", "justifyContent": "space-between", "alignItems": "center",
            "padding": "12px 24px", "backgroundColor": "#1a1a2e", "color": "#eee",
        }),

        # Summary banner
        html.Div([
            html.Div(id="summary-banner", style={"flex": "1"}),
            html.Div([
                html.Label("Time Unit: ", style={"marginRight": "4px", "fontSize": "13px"}),
                dcc.RadioItems(
                    id="time-unit-toggle",
                    options=[
                        {"label": "ms", "value": "ms"},
                        {"label": "s", "value": "s"},
                    ],
                    value="ms",
                    inline=True,
                    inputStyle={"marginRight": "3px"},
                    labelStyle={"marginRight": "10px", "fontSize": "13px"},
                ),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={
            "display": "flex", "justifyContent": "space-between", "alignItems": "center",
            "padding": "8px 24px", "backgroundColor": "#16213e", "color": "#aaa",
            "fontSize": "13px",
        }),

        # Loading indicator
        dcc.Loading(
            id="loading-indicator",
            type="circle",
            children=html.Div(id="loading-target"),
        ),

        # Global filter panel
        filter_panel_layout(),

        # Tabs
        dcc.Tabs(id="main-tabs", value="timeline", children=[
            dcc.Tab(label="Timeline Heatmap", value="timeline"),
            dcc.Tab(label="Statistics", value="statistics"),
            dcc.Tab(label="Bottleneck Analysis", value="bottleneck"),
        ], style={"margin": "0 24px"}),

        # Tab content
        html.Div(id="tab-content", style={"padding": "16px 24px"}),
    ])
