"""Global filter callbacks — apply filters, populate options, cache filtered df.

Responsibilities:
    - Use a pattern-matching callback on ALL {"type": "global-filter"} components
      to react when any global filter value changes.
    - Iterate FILTER_REGISTRY and call each filter's apply_filter(df, value)
      in sequence, starting from the full cached dataset.
    - Store the result via set_filtered_df() for tab callbacks to consume.
    - Increment filtered-data-version so downstream callbacks re-fire.
    - Populate value filter dropdown options when data-store changes.

Public functions:
    register_filter_callbacks(app) -> None

Dash callbacks registered (2):
    apply_filters      — Input: {"type": "global-filter", "index": ALL},
                          data-store;
                          Output: filtered-data-version
    populate_options   — Input: data-store;
                          Output: {"type": "global-filter", "index": ALL} options

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import Input, Output, ALL

from callbacks.data_callbacks import get_cached_dataset
from filters import FILTER_REGISTRY, get_filtered_df, set_filtered_df


def register_filter_callbacks(app):
    # Build lookup: filter_id -> FilterDef
    _filter_lookup = {f.filter_id: f for f in FILTER_REGISTRY}

    @app.callback(
        Output("filtered-data-version", "data"),
        Input({"type": "global-filter", "index": ALL}, "value"),
        Input("data-store", "data"),
    )
    def apply_filters(filter_values, store_data):
        """Apply all global filters in registry order and cache the result."""
        if not store_data or not store_data.get("loaded"):
            set_filtered_df(None)
            return 0

        dataset = get_cached_dataset()
        if not dataset:
            set_filtered_df(None)
            return 0

        df = dataset["df"]

        # filter_values is a list ordered by the pattern-matching index.
        # We need to map each value back to its filter_id.
        # Dash delivers ALL-pattern values in the order the components
        # appear in the layout, which matches FILTER_REGISTRY order since
        # filter_panel_layout() iterates the registry.
        for i, fdef in enumerate(FILTER_REGISTRY):
            if i < len(filter_values):
                val = filter_values[i]
            else:
                val = None
            df = fdef.apply_filter(df, val)

        set_filtered_df(df)

        # Use length of filtered df as a pseudo-version; downstream just
        # needs to see a change.
        return len(df)

    @app.callback(
        Output({"type": "global-filter", "index": ALL}, "options"),
        Input("data-store", "data"),
    )
    def populate_options(store_data):
        """Populate dropdown options for all value filters from store data."""
        results = []
        for fdef in FILTER_REGISTRY:
            if fdef.get_options and store_data and store_data.get("loaded"):
                results.append(fdef.get_options(store_data))
            else:
                # Semantic filters (toggles) don't need dynamic options;
                # return their static options list from the component.
                # Dash requires us to return *something* for each matched output.
                if fdef.category == "semantic":
                    # Return the existing options unchanged (checklist options)
                    results.append([{"label": f" {fdef.label}",
                                     "value": fdef.filter_id}])
                else:
                    results.append([])
        return results
