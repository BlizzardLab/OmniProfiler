"""Layout components package.

This package contains Dash layout modules that define the UI structure
for each section of the application. Layout modules produce component
trees (html.Div, dcc.Graph, etc.) but contain no callback logic.

Modules:
    main_layout  — top-level page (header, summary banner, tabs)
    timeline     — Timeline Heatmap tab
    statistics   — Statistics tab

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""
