"""No USE After RELEASE semantic filter — removes non-final RELEASE events.

Responsibilities:
    - Register a semantic (toggle) filter.
    - When enabled, examine the per-ptr event timeline and remove RELEASE
      events that are followed by a USE on the same address (indicating the
      release was not final).

Filter logic:
    1. Group events by ptr (resource address).
    2. Within each ptr group, sort by ts_ns.
    3. For each RELEASE event, check if any USE event occurs later on the
       same ptr.
    4. If yes, mark that RELEASE event for removal.
    5. Return df with those RELEASE rows removed.

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

from dash import dcc

from filters.registry import FilterDef, register


def _component():
    return dcc.Checklist(
        id={"type": "global-filter", "index": "no_use_after_release"},
        options=[{"label": " No USE After RELEASE", "value": "no_use_after_release"}],
        value=[],  # OFF by default
        inputStyle={"marginRight": "4px"},
        style={"fontSize": "13px"},
    )


def _apply(df, value):
    if not value:  # empty list = OFF
        return df

    # Only process if we have both RELEASE and USE events
    if "has_release" not in df.columns or "has_use" not in df.columns:
        return df

    release_df = df[df["has_release"]]
    if len(release_df) == 0:
        return df

    use_df = df[df["has_use"]]
    if len(use_df) == 0:
        return df

    remove_idx = []
    for ptr, group in df.groupby("ptr"):
        group = group.sort_values("ts_ns")
        release_mask = group["has_release"]
        use_mask = group["has_use"]
        release_indices = group.index[release_mask]
        use_ts = group.loc[use_mask, "ts_ns"].values

        if len(use_ts) == 0:
            continue

        for idx in release_indices:
            release_ts = group.loc[idx, "ts_ns"]
            if (use_ts > release_ts).any():
                remove_idx.append(idx)

    if remove_idx:
        return df.drop(index=remove_idx)
    return df


register(FilterDef(
    filter_id="no_use_after_release",
    label="No USE After RELEASE",
    category="semantic",
    make_component=_component,
    apply_filter=_apply,
    get_options=None,
))
