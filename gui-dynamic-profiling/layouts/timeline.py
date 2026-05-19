"""Timeline Heatmap tab layout.

Responsibilities:
    - Resource type dropdown for filtering events.
    - Event type checklist (USE, RELEASE, ACQUIRE, WAIT, ACCESS, GET) for toggling categories.
    - Time bin slider to control heatmap granularity.
    - Heatmap graph container (no fixed CSS height; figure controls its own size).
    - Below-heatmap click-detail panel.  Container is invisible when empty;
      max-height scroll keeps the populated panel bounded.

Public functions:
    timeline_layout() -> html.Div

Dash component IDs exposed:
    timeline-resource-dropdown, timeline-event-checklist,
    timeline-bins-slider, timeline-heatmap, timeline-detail

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import dcc, html


# Scroll container style — applied to wrapper divs so callback content
# stays within a bounded height.  No visible border/background so the
# containers are invisible when empty.
_SCROLL_STYLE = {
    "maxHeight": "420px",
    "overflowY": "auto",
}


def timeline_layout():
    return html.Div([
        html.H3("Timeline Heatmap", style={"marginTop": "0"}),
        html.P("Event density across threads over time. Click a cell to inspect events.",
               style={"color": "#666", "fontSize": "13px"}),

        # Controls row
        html.Div([
            html.Div([
                html.Label("Resource Type", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Dropdown(id="timeline-resource-dropdown", placeholder="All resources",
                             style={"width": "220px"}),
            ], style={"marginRight": "20px"}),
            html.Div([
                html.Label("Event Types", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Checklist(
                    id="timeline-event-checklist",
                    options=[
                        {"label": " USE", "value": "USE"},
                        {"label": " RELEASE", "value": "RELEASE"},
                        {"label": " ACQUIRE", "value": "ACQUIRE"},
                        {"label": " WAIT", "value": "WAIT"},
                        {"label": " ACCESS", "value": "ACCESS"},
						{"label": " GET", "value": "GET"},
                    ],
                    value=[],
                    inline=True,
                    style={"fontSize": "13px"},
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"marginRight": "12px"},
                ),
            ], style={"marginRight": "20px"}),
            html.Div([
                html.Label("Time Bins", style={"fontWeight": "bold", "fontSize": "13px"}),
                dcc.Slider(
                    id="timeline-bins-slider",
                    min=20, max=500, step=10, value=250,
                    marks={20: "20", 100: "100", 250: "250", 500: "500"},
                    tooltip={"placement": "bottom"},
                ),
            ], style={"width": "250px"}),
        ], style={"display": "flex", "alignItems": "flex-end", "flexWrap": "wrap",
                   "gap": "8px", "marginBottom": "16px"}),

        # Heatmap — no fixed CSS height; the figure's own layout.height
        # (set dynamically by the callback) controls the rendered size.
        dcc.Graph(id="timeline-heatmap"),

        # Click-detail panel
        # Container is invisible when empty (no border/background);
        # maxHeight + overflowY keep it bounded when populated.
        html.Div(
            id="timeline-detail",
            style={**_SCROLL_STYLE, "marginTop": "12px"},
        ),
    ])
