"""Global filter panel layout — renders all registered filters.

Responsibilities:
    - Iterate FILTER_REGISTRY and render value filters (dropdowns) in a
      horizontal row with a "Global Filters" label.
    - Render semantic filters (toggles) in a separate section below with
      descriptions.
    - Expose filter_panel_layout() for inclusion in the main layout.

Public functions:
    filter_panel_layout() -> html.Div

Dash component IDs exposed:
    {"type": "global-filter", "index": <filter_id>}  — one per registered filter
    filter-panel  — wrapper div for the entire filter panel

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import html

from filters.registry import FILTER_REGISTRY


def filter_panel_layout():
    """Build the global filter panel from the filter registry."""
    value_filters = [f for f in FILTER_REGISTRY if f.category == "value"]
    semantic_filters = [f for f in FILTER_REGISTRY if f.category == "semantic"]

    children = []

    # Value filters row
    if value_filters:
        filter_items = []
        for fdef in value_filters:
            filter_items.append(html.Div([
                html.Label(fdef.label, style={
                    "fontWeight": "bold", "fontSize": "12px", "color": "#ccc",
                    "marginBottom": "4px",
                }),
                fdef.make_component(),
            ], style={"marginRight": "12px", "flex": "1", "minWidth": "150px"}))

        children.append(html.Div([
            html.Div(filter_items, style={
                "display": "flex", "alignItems": "flex-end",
                "flexWrap": "wrap", "gap": "8px", "flex": "1",
            }),
        ], style={"display": "flex", "alignItems": "flex-end"}))

    # Semantic filters row
    if semantic_filters:
        toggle_items = []
        for fdef in semantic_filters:
            toggle_items.append(html.Div([
                fdef.make_component(),
            ], style={"marginRight": "20px"}))

        children.append(html.Div(
            toggle_items,
            style={
                "display": "flex", "alignItems": "center",
                "flexWrap": "wrap", "gap": "4px",
                "marginTop": "6px" if value_filters else "0",
            },
        ))

    return html.Div([
        html.Div([
            html.Span("Global Filters", style={
                "fontWeight": "bold", "fontSize": "13px", "color": "#eee",
                "marginRight": "16px", "whiteSpace": "nowrap",
            }),
        ], style={"marginBottom": "6px"}),
        *children,
    ], id="filter-panel", style={
        "padding": "10px 24px",
        "backgroundColor": "#0f3460",
        "borderBottom": "1px solid #1a1a2e",
    })
