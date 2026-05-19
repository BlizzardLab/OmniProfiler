"""Thread value filter — multi-select dropdown for threads.

Responsibilities:
    - Register a value filter that lets users select one or more threads.
    - Provide dropdown options derived from store_data["thread_labels"].
    - Filter the DataFrame to rows matching the selected thread labels.

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import dcc

from filters.registry import FilterDef, register


def _component():
    return dcc.Dropdown(
        id={"type": "global-filter", "index": "thread"},
        multi=True,
        placeholder="All threads",
        style={"minWidth": "180px"},
    )


def _apply(df, value):
    if not value:
        return df
    return df[df["thread_label"].isin(value)]


def _options(store_data):
    return [{"label": f"Thread {t}", "value": t}
            for t in store_data.get("thread_labels", [])]


register(FilterDef(
    filter_id="thread",
    label="Thread",
    category="value",
    make_component=_component,
    apply_filter=_apply,
    get_options=_options,
))
