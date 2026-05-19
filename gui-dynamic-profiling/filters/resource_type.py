"""Resource Type value filter — multi-select dropdown for resource types.

Responsibilities:
    - Register a value filter that lets users select one or more resource types.
    - Provide dropdown options derived from store_data["resource_types"].
    - Filter the DataFrame to rows matching the selected resource types.

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import dcc

from filters.registry import FilterDef, register


def _component():
    return dcc.Dropdown(
        id={"type": "global-filter", "index": "resource_type"},
        multi=True,
        placeholder="All resource types",
        style={"minWidth": "220px"},
    )


def _apply(df, value):
    if not value:
        return df
    return df[df["resource_type"].isin(value)]


def _options(store_data):
    return [{"label": r, "value": r}
            for r in sorted(store_data.get("resource_types", []))]


register(FilterDef(
    filter_id="resource_type",
    label="Resource Type",
    category="value",
    make_component=_component,
    apply_filter=_apply,
    get_options=_options,
))
