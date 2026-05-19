"""Dynamic Profiling Explorer — application entry point.

Responsibilities:
    - Parse CLI arguments for an optional data directory path.
    - Create and configure the Dash application instance.
    - Register all layout components and callback modules, including
      global filter callbacks.
    - Implement tab-switching logic (Timeline / Statistics /
      Bottleneck Analysis).
    - Launch the development server and open the browser.

Public functions:
    create_app(data_dir) -> Dash   — build the configured app
    main()                         — CLI entry point

Depends on:
    layouts.main_layout, layouts.timeline, layouts.statistics,
    layouts.bottleneck,
    callbacks.data_callbacks, callbacks.filter_cb, callbacks.timeline_cb,
    callbacks.statistics_cb, callbacks.bottleneck_cb

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

import sys
sys.dont_write_bytecode = True
import webbrowser
import threading

from dash import Dash, Input, Output

from layouts.main_layout import make_layout
from layouts.timeline import timeline_layout
from layouts.statistics import statistics_layout
from layouts.bottleneck import bottleneck_layout
from callbacks.data_callbacks import register_data_callbacks, preload_data
from callbacks.filter_cb import register_filter_callbacks
from callbacks.timeline_cb import register_timeline_callbacks
from callbacks.statistics_cb import register_statistics_callbacks
from callbacks.bottleneck_cb import register_bottleneck_callbacks


def create_app(data_dir: str = ""):
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.title = "Dynamic Profiling Explorer"

    # Pre-load data if directory provided
    initial_store_data = None
    if data_dir:
        print(f"Pre-loading data from: {data_dir}")
        initial_store_data = preload_data(data_dir)
        print(f"Loaded {initial_store_data['num_events']:,} events from {initial_store_data['num_threads']} threads")

    app.layout = make_layout(initial_data_dir=data_dir)

    # Register callbacks
    register_data_callbacks(app, initial_store_data=initial_store_data)
    register_filter_callbacks(app)
    register_timeline_callbacks(app)
    register_statistics_callbacks(app)
    register_bottleneck_callbacks(app)

    # Tab switching callback
    @app.callback(
        Output("tab-content", "children"),
        Input("main-tabs", "value"),
    )
    def render_tab(tab):
        if tab == "timeline":
            return timeline_layout()
        elif tab == "statistics":
            return statistics_layout()
        elif tab == "bottleneck":
            return bottleneck_layout()
        return ""

    return app


def main():
    data_dir = "demo-case/MDL/outputs/omniprofiler"  # Default sample data directory
    if len(sys.argv) > 1:
        data_dir = sys.argv[1]

    app = create_app(data_dir)

    port = 8050
    # Open browser after a short delay
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    app.run(debug=False, port=port)


if __name__ == "__main__":
    main()
