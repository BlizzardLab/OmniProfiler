"""Callback modules package.

This package contains Dash callback registration functions that wire
user interactions (clicks, dropdown changes, slider drags) to UI updates.
Each module provides a register_*_callbacks(app) function called by app.py.

Modules:
    data_callbacks   — data loading, caching, summary banner
    timeline_cb      — timeline heatmap rendering and click-to-detail
    statistics_cb    — statistics charts, function table, time filtering

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""
