"""Function Name value filter — searchable multi-select dropdown for functions.

Responsibilities:
    - Register a value filter that lets users select one or more function names.
    - Provide dropdown options derived from the cached dataset's unique
      function names (top 200 by event count to keep the dropdown manageable).
    - Filter the DataFrame to rows matching the selected function names.

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import dcc

from filters.registry import FilterDef, register


def _component():
    return dcc.Dropdown(
        id={"type": "global-filter", "index": "function_name"},
        multi=True,
        placeholder="All functions",
        searchable=True,
        style={"minWidth": "300px"},
    )


def _apply(df, value):
    if not value:
        return df
    return df[df["function_name"].isin(value)]


def _options(store_data):
    from callbacks.data_callbacks import get_cached_dataset
    dataset = get_cached_dataset()
    if not dataset or "df" not in dataset:
        return []
    df = dataset["df"]
    # Top 200 functions by event count
    top = df["function_name"].value_counts().head(200)
    return [{"label": f"{name} ({count})", "value": name}
            for name, count in top.items()]


register(FilterDef(
    filter_id="function_name",
    label="Function Name",
    category="value",
    make_component=_component,
    apply_filter=_apply,
    get_options=_options,
))
