"""Bottleneck Analysis tab callbacks.

Responsibilities:
    - Populate resource type and thread filter dropdowns, configure the
      time window RangeSlider based on loaded data and current time unit.
    - Render a Contention Scoreboard: resource type contention bar chart
      (WAIT/addr ratio per type sorted descending, with WAIT count and
      unique addresses on hover).
    - Render a Top Contended Addresses horizontal bar chart driven by
      clicking a bar in the resource type chart; shows top 15 addresses
      for the clicked resource type ranked by total WAIT duration
      descending. Displays a prompt message by default until a bar is
      clicked.
    - Render a Multi-Layer Cascading Contention Map (Sankey) driven by
      clicking a resource type bar, combined with a Temporal Contention
      Heatmap that shows per-thread WAIT wall-time duration for the
      addresses and threads present in the Sankey diagram. Both are
      blank until a resource type bar is clicked.
      Sankey link values represent WAIT event pair counts (matched
      entry/exit pairs); address nodes are ranked by pair count in
      descending order. Uses a two-phase BFS: Phase 1 discovers
      associated resource types via shared functions using raw events
      (no WAIT interval requirement), storing per-layer data; Phase 2
      iterates discovered layers, computes WAIT pair counts from the
      full dataset, and builds Sankey nodes/links.
      Layer 0: addr→func→thread. Subsequent layers discover new
      addresses on unseen resource types; the new addresses link to
      previous-layer functions (new_addr→prev_func→thread) using raw
      event associations (not requiring WAIT pairs), with the addr's
      WAIT pair count as the link value, colored as the new layer.
      Within the new layer: new_addr→new_func→thread. Cascade depth
      dropdown (0–3) controls expansion. Per-layer explore/display
      sliders control how many addresses drive BFS vs. how many are
      shown. Nodes and links are colored per layer: blue (L0),
      orange (L1), green (L2), purple (L3). A min node flow filter
      (default 2) removes nodes whose total flow count falls below
      the threshold. Node type metadata (addr/func/thread), link
      structure, and default link colors are stored in
      fig.layout.meta for clientside callbacks. The Sankey uses
      arrangement="fixed" (nodes are not draggable) to enable
      plotly_click events on nodes.
    - Clientside hover highlighting: when any node (address, function,
      or thread) is hovered in the Sankey diagram, only links that
      come from real trace (ptr, function, thread) triples involving
      the hovered node are marked red; non-associated links are
      dimmed.  Detection is grounded in addr_thread_funcs /
      triple_link_map shipped via fig.layout.meta — NOT in Sankey
      graph reachability — so hovering an addr never lights up
      threads that share a function with it on a different addr,
      and hovering a thread never lights up addrs the thread never
      reached.  Func hover highlights links whose endpoint is the
      func itself (already trace-true).  Suppressed while click-
      highlight is active.
    - Clientside click highlighting (thread-pair shared contention):
      clicking two thread nodes consecutively highlights all shared
      resource addresses (addresses whose real trace contains
      (addr, func, thread) triples reaching BOTH selected threads),
      the connecting function nodes, and the corresponding links in
      red.  Detection is grounded in real (ptr, function_name,
      thread_label) triples computed serverside (addr_thread_funcs,
      triple_link_map shipped via fig.layout.meta) — NOT in Sankey
      graph reachability — so an address only touched by T1 through
      func F is never falsely marked shared with T2 just because F
      also reached T2 on a different address.  Non-highlighted nodes
      and links are dimmed.  A Reset button clears the selection and
      restores default colors.  When two threads are selected, a
      Shared Contention Functions table is populated between the
      Sankey and the heatmap, showing two parts (one per thread)
      separated by a horizontal line, each listing highlighted
      functions in descending order by total WAIT duration summed
      ONLY over the shared addresses for that (function, thread)
      pair (using addr_func_thread_durations from fig.layout.meta).
      The table is cleared on reset or figure update.
    - Toggle visibility of per-layer slider rows based on cascade depth.
    - All charts honour resource type/thread filters, time window,
      time unit toggle, and global filters via get_filtered_df() and
      filtered-data-version.

Public functions:
    register_bottleneck_callbacks(app) -> None

Dash callbacks registered (4 + 2 clientside):
    update_controls           — Input: data-store, time-unit-toggle;
                                 Output: bottleneck-resource-dropdown,
                                 bottleneck-thread-dropdown,
                                 bottleneck-time-range (min/max/value/step/marks),
                                 bottleneck-time-label
    update_restype_bar        — Input: data-store, bottleneck-resource-dropdown,
                                 bottleneck-thread-dropdown,
                                 bottleneck-time-range, time-unit-toggle,
                                 filtered-data-version;
                                 Output: bottleneck-restype-bar
    update_addr_bar           — Input: bottleneck-restype-bar clickData,
                                 data-store, bottleneck-resource-dropdown,
                                 bottleneck-thread-dropdown,
                                 bottleneck-time-range, time-unit-toggle,
                                 filtered-data-version;
                                 Output: bottleneck-addr-bar
    update_cascade            — Input: bottleneck-restype-bar clickData,
                                 data-store, bottleneck-resource-dropdown,
                                 bottleneck-thread-dropdown,
                                 bottleneck-time-range, bottleneck-bins-slider,
                                 time-unit-toggle, filtered-data-version,
                                 bottleneck-cascade-depth,
                                 bottleneck-cascade-explore-0..3,
                                 bottleneck-cascade-display-0..3,
                                 bottleneck-cascade-min-flow;
                                 Output: bottleneck-cascade-sankey,
                                 bottleneck-temporal-heatmap
    toggle_layer_sliders      — Input: bottleneck-cascade-depth;
                                 Output: bottleneck-cascade-row-0..3 style
    (clientside) node_hover   — Input: bottleneck-cascade-sankey figure;
                                 Output: bottleneck-hover-dummy children;
                                 Attaches plotly_hover/unhover/click
                                 listeners. Hover highlights associated
                                 links. Click on thread nodes tracks
                                 selection (max 2); when 2 selected,
                                 highlights shared addr/func/links and
                                 populates bottleneck-shared-table with
                                 per-thread function durations.
    (clientside) reset_click  — Input: bottleneck-cascade-reset n_clicks;
                                 Output: bottleneck-hover-dummy style;
                                 Clears thread selection, restores
                                 default node/link colors, and clears
                                 the shared contention table.

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, html

from callbacks.data_callbacks import get_cached_dataset
from filters import get_filtered_df


def _time_divisor(unit):
    return 1e9 if unit == "s" else 1e6


def _time_label(unit):
    return "s" if unit == "s" else "ms"


def _apply_time_filter(df, time_range, time_unit):
    """Filter df to the selected time window."""
    if time_range and len(time_range) == 2:
        divisor = _time_divisor(time_unit)
        t_lo, t_hi = time_range
        ts = df["ts_relative_ns"] / divisor
        df = df[(ts >= t_lo) & (ts <= t_hi)]
    return df


def _empty_fig(message="No data"):
    fig = go.Figure()
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(text=message, xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=16, color="#888"))],
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig


def _compute_wait_intervals(df):
    """Pair WAIT entry/exit events using backward analysis.

    Groups WAIT events by (thread_id, function_index, ptr), sorts descending
    by timestamp, LIFO-matches exits to entries.  Orphan WAITs (entry with no
    exit) are discarded.

    Returns list of dicts with keys: start, end, resource_type, function_name,
    thread_label, thread_id, ptr.
    """
    wait_df = df[df["has_wait"]].copy()
    if len(wait_df) == 0:
        return []

    intervals = []
    grouped = wait_df.groupby(["thread_id", "function_index", "ptr"])
    for (tid, func_idx, ptr), group in grouped:
        events = group.sort_values(["ts_relative_ns", "is_exit"],
                                   ascending=[False, False])
        pending_exits = []
        for _, ev in events.iterrows():
            if ev["is_exit"]:
                pending_exits.append(ev)
            else:
                if pending_exits:
                    exit_ev = pending_exits.pop()  # LIFO: match nearest exit
                    start = ev["ts_relative_ns"]
                    end = exit_ev["ts_relative_ns"]
                    if end > start:
                        intervals.append({
                            "start": start,
                            "end": end,
                            "resource_type": ev["resource_type"],
                            "function_name": ev["function_name"],
                            "thread_label": ev["thread_label"],
                            "thread_id": tid,
                            "ptr": ptr,
                        })
        # Remaining pending_exits are pre-trace exits (ringbuffer cutoff) — discard
    return intervals


def _rank_ptrs_by_wait_duration(df):
    """Rank pointers by total WAIT duration descending.

    Computes WAIT intervals via _compute_wait_intervals, sums duration
    per ptr.  Returns a pd.Series (ptr -> total_duration_ns) sorted
    descending, or an empty Series if no intervals are found.
    """
    intervals = _compute_wait_intervals(df)
    if not intervals:
        return pd.Series(dtype=float)
    iv_df = pd.DataFrame(intervals)
    iv_df["duration"] = iv_df["end"] - iv_df["start"]
    return iv_df.groupby("ptr")["duration"].sum().sort_values(ascending=False)


def _get_df(store_data):
    """Get the working DataFrame from filtered cache or raw cache."""
    if not store_data or not store_data.get("loaded"):
        return None
    df = get_filtered_df()
    if df is None:
        dataset = get_cached_dataset()
        if not dataset:
            return None
        df = dataset["df"]
    return df


# ── Layer color scheme ───────────────────────────────────────────────────
_LAYER_NODE_COLORS = ["#3498db", "#e67e22", "#27ae60", "#8e44ad"]
_LAYER_LINK_COLORS = [
    "rgba(52,152,219,0.4)",
    "rgba(230,126,34,0.4)",
    "rgba(39,174,96,0.4)",
    "rgba(142,68,173,0.4)",
]


def _build_cascade_sankey(full_df, clicked_rt, max_depth,
                          explore_limits, display_limits, min_flow=2,
                          time_unit="ms"):
    """Build a multi-layer cascading Sankey diagram via two-phase BFS.

    Layer 0: seed from clicked resource type (WAIT events only).

    Phase 1 — BFS discovery (layers 1..max_depth): expand from NEW
    functions discovered at the previous layer, query full_df for
    those functions on resource types NOT yet seen, discover new
    addresses and functions using raw events (no WAIT interval
    computation).  This ensures BFS can traverse through functions
    even when they have no WAIT pairs on the new resource types.

    Phase 2 — Pair count calculation & Sankey building: iterate over
    the layers discovered in Phase 1, compute WAIT intervals from
    the full dataset for each layer's display ptrs, and build Sankey
    nodes/links.  Layers with no WAIT pairs are skipped without
    halting BFS.  Cross-layer links (new_addr→prev_func→thread) use
    raw event associations to find which expand_funcs connect to
    which display ptrs, with the addr's total WAIT pair count as the
    link value; func→thread links are also created from raw events
    so expand_funcs are never orphaned without outgoing links.

    All link values represent WAIT event pair counts (matched
    entry/exit pairs).  Address nodes are added in descending pair
    count order.

    After BFS, nodes whose total flow count (number of incoming +
    outgoing links) is below min_flow are removed along with their links.

    Returns a go.Figure with Sankey diagram.
    """
    # All node labels, colors, and index mapping
    all_labels = []
    all_colors = []
    node_index = {}  # unique key -> index in all_labels

    sources, targets, values, link_colors = [], [], [], []
    all_seen_rts = set()        # resource types seen across all layers
    all_seen_funcs = set()      # functions seen across all layers
    all_seen_ptrs = set()       # ptrs seen across all layers
    all_seen_threads = set()    # threads seen across all layers
    new_funcs_this_layer = set()  # functions discovered at current layer

    def _add_node(key, label, color):
        """Add a node if not already present; return its index."""
        if key not in node_index:
            node_index[key] = len(all_labels)
            all_labels.append(label)
            all_colors.append(color)
        return node_index[key]

    def _add_link(src_idx, tgt_idx, value, color):
        sources.append(src_idx)
        targets.append(tgt_idx)
        values.append(value)
        link_colors.append(color)

    # ── Layer 0: seed from clicked resource type ────────────────────────
    rt_df = full_df[full_df["resource_type"] == clicked_rt]
    wait_df = rt_df[rt_df["has_wait"]]
    if len(wait_df) == 0:
        return _empty_fig(f"No WAIT events for {clicked_rt}"), set(), set()

    layer_color_node = _LAYER_NODE_COLORS[0]
    layer_color_link = _LAYER_LINK_COLORS[0]
    explore_n = explore_limits[0]
    display_n = display_limits[0]

    # Compute WAIT intervals for this resource type
    intervals_0 = _compute_wait_intervals(rt_df)
    if not intervals_0:
        return _empty_fig(f"No WAIT entry/exit pairs for {clicked_rt}"), set(), set()
    iv_df_0 = pd.DataFrame(intervals_0)

    # Rank ptrs by WAIT pair count
    ptr_counts_0 = iv_df_0.groupby("ptr").size().sort_values(ascending=False)
    explore_ptrs_0 = set(ptr_counts_0.head(explore_n).index)
    display_ptrs_0 = set(ptr_counts_0.head(display_n).index)
    explore_ptrs_0 = explore_ptrs_0 | display_ptrs_0

    all_seen_rts.add(clicked_rt)
    all_seen_ptrs.update(explore_ptrs_0)

    # Build links from displayed ptrs using WAIT pair counts
    display_iv = iv_df_0[iv_df_0["ptr"].isin(display_ptrs_0)]
    _duration_frames = [display_iv]
    # Collect (ptr, function_name, thread_label) triples that are actually
    # present in the trace.  Used to ground click-highlight contention
    # detection in real co-occurrences instead of Sankey graph
    # reachability.  Layer 0 + new_func (layer >= 1) triples come from
    # WAIT intervals (already in _duration_frames); expand_func
    # (layer >= 1) triples come from raw events and are added below.
    _trace_triple_frames = []
    triple_counts = (display_iv
                     .groupby(["ptr", "function_name", "thread_label"])
                     .size().reset_index(name="count"))
    triple_counts = triple_counts[triple_counts["count"] > 0]

    if len(triple_counts) == 0:
        return _empty_fig(f"No significant WAIT relationships for {clicked_rt}"), set(), set()

    # Pre-add address nodes in descending pair count order
    display_ptr_counts = ptr_counts_0[ptr_counts_0.index.isin(display_ptrs_0)]
    for ptr in display_ptr_counts.index:
        _add_node(f"addr:{ptr}", f"{clicked_rt}:{ptr[-8:]}", layer_color_node)

    # Create func and thread nodes
    for _, row in triple_counts.iterrows():
        _add_node(f"func:{row['function_name']}", row["function_name"], layer_color_node)
        _add_node(f"thread:{row['thread_label']}", f"T{row['thread_label']}", layer_color_node)
        all_seen_funcs.add(row["function_name"])
        all_seen_threads.add(row["thread_label"])

    # Aggregate addr->func links (pair count)
    pf = triple_counts.groupby(["ptr", "function_name"])["count"].sum().reset_index()
    for _, row in pf.iterrows():
        _add_link(
            node_index[f"addr:{row['ptr']}"],
            node_index[f"func:{row['function_name']}"],
            int(row["count"]),
            layer_color_link,
        )
    # Aggregate func->thread links (pair count)
    ft = triple_counts.groupby(["function_name", "thread_label"])["count"].sum().reset_index()
    for _, row in ft.iterrows():
        _add_link(
            node_index[f"func:{row['function_name']}"],
            node_index[f"thread:{row['thread_label']}"],
            int(row["count"]),
            layer_color_link,
        )

    # Collect functions from explored ptrs (any event, for BFS expansion)
    explore_events = rt_df[rt_df["ptr"].isin(explore_ptrs_0)]
    explore_funcs = set(explore_events["function_name"].unique())
    new_funcs_this_layer = explore_funcs

    # ── Phase 1: BFS discovery (layers 1..max_depth) ─────────────────────
    # Discover addresses and functions at each layer using raw events.
    # No WAIT interval computation here — just find associations.
    bfs_layers = []
    for layer in range(1, max_depth + 1):
        expand_funcs = new_funcs_this_layer - (all_seen_funcs - new_funcs_this_layer)
        if not expand_funcs:
            break

        # Mark expand funcs as seen before discovering new ones
        all_seen_funcs.update(expand_funcs)

        explore_n = explore_limits[min(layer, 3)]
        display_n = display_limits[min(layer, 3)]

        # Find events for expand_funcs on resource types NOT yet seen
        func_df = full_df[
            (full_df["function_name"].isin(expand_funcs)) &
            (~full_df["resource_type"].isin(all_seen_rts))
        ]
        if len(func_df) == 0:
            break

        # Discover ptrs from events (rank by event count for BFS selection)
        ptr_counts = func_df.groupby("ptr").size().sort_values(ascending=False)
        explore_ptrs = set(ptr_counts.head(explore_n).index)
        display_ptrs = set(ptr_counts.head(display_n).index)
        explore_ptrs = explore_ptrs | display_ptrs

        if not explore_ptrs:
            break

        # Track new resource types
        new_rts = set(func_df[func_df["ptr"].isin(explore_ptrs)]["resource_type"].unique())
        all_seen_rts.update(new_rts)

        # Discover new functions that interact with explore ptrs
        other_func_df = full_df[
            (full_df["ptr"].isin(explore_ptrs)) &
            (~full_df["function_name"].isin(all_seen_funcs))
        ]
        next_new_funcs = (set(other_func_df["function_name"].unique())
                          if len(other_func_df) > 0 else set())

        bfs_layers.append({
            "layer": layer,
            "expand_funcs": expand_funcs,
            "display_ptrs": display_ptrs,
            "new_rts": new_rts,
            "next_new_funcs": next_new_funcs,
        })

        all_seen_funcs.update(next_new_funcs)
        all_seen_ptrs.update(explore_ptrs)
        new_funcs_this_layer = next_new_funcs

    # ── Phase 2: WAIT pair count calculation & Sankey building ─────────
    # For each BFS layer, compute WAIT pair counts from the full dataset
    # and build Sankey nodes/links.
    for ld in bfs_layers:
        layer = ld["layer"]
        layer_color_node = _LAYER_NODE_COLORS[min(layer, 3)]
        layer_color_link = _LAYER_LINK_COLORS[min(layer, 3)]
        display_ptrs = ld["display_ptrs"]
        expand_funcs = ld["expand_funcs"]
        next_new_funcs = ld["next_new_funcs"]

        # Compute WAIT intervals for display ptrs from full dataset
        ptr_full_df = full_df[full_df["ptr"].isin(display_ptrs)]
        intervals = _compute_wait_intervals(ptr_full_df)
        if not intervals:
            continue

        iv_df = pd.DataFrame(intervals)

        # Keep only intervals from the new RTs discovered at this layer
        iv_df = iv_df[iv_df["resource_type"].isin(ld["new_rts"])]
        if len(iv_df) == 0:
            continue
        _duration_frames.append(iv_df)

        # Rank address nodes by WAIT pair count
        ptr_pair_counts = iv_df.groupby("ptr").size().sort_values(ascending=False)

        # Pre-add address nodes in descending pair count order
        for ptr in ptr_pair_counts[ptr_pair_counts.index.isin(display_ptrs)].index:
            ptr_rt = iv_df.loc[iv_df["ptr"] == ptr, "resource_type"].iloc[0]
            _add_node(f"addr:{ptr}", f"{ptr_rt}:{ptr[-8:]}", layer_color_node)

        # ef_links: addr → expand_func (previous-layer functions that led
        # to discovering these addresses).  Use raw events to find the
        # association because expand_funcs may not have WAIT pairs on
        # these ptrs — they were discovered via any event type in BFS.
        # Link value = addr's total WAIT pair count.
        # Also create expand_func → thread links so func nodes are not
        # orphaned at the rightmost position.
        ef_raw = full_df[
            (full_df["function_name"].isin(expand_funcs)) &
            (full_df["ptr"].isin(display_ptrs))
        ]
        if len(ef_raw) > 0:
            ef_pairs = ef_raw.groupby(["ptr", "function_name"]).size().reset_index(
                name="cnt")

            for _, row in ef_pairs.iterrows():
                ptr = row["ptr"]
                if ptr not in ptr_pair_counts.index:
                    continue
                count_val = int(ptr_pair_counts[ptr])
                if count_val <= 0:
                    continue
                ptr_key = f"addr:{ptr}"
                func_key = f"func:{row['function_name']}"
                _add_node(func_key, row["function_name"], layer_color_node)
                _add_link(
                    node_index[ptr_key],
                    node_index[func_key],
                    count_val,
                    layer_color_link,
                )

            # expand_func → thread links (using raw events and addr pair counts)
            ef_triples = (ef_raw
                .drop_duplicates(subset=["ptr", "function_name", "thread_label"])
                .copy())
            ef_triples = ef_triples[ef_triples["ptr"].isin(ptr_pair_counts.index)]
            ef_triples["pair_count"] = ef_triples["ptr"].map(ptr_pair_counts).astype(int)
            ef_triples = ef_triples[ef_triples["pair_count"] > 0]

            if len(ef_triples) > 0:
                # Record raw-event triples for trace-grounded click highlight
                _trace_triple_frames.append(
                    ef_triples[["ptr", "function_name", "thread_label"]])
                ef_ft = (ef_triples
                    .groupby(["function_name", "thread_label"])["pair_count"]
                    .sum().reset_index())

                for _, row in ef_ft.iterrows():
                    func_key = f"func:{row['function_name']}"
                    thread_key = f"thread:{row['thread_label']}"
                    _add_node(func_key, row["function_name"], layer_color_node)
                    _add_node(thread_key, f"T{row['thread_label']}", layer_color_node)
                    _add_link(
                        node_index[func_key],
                        node_index[thread_key],
                        int(row["pair_count"]),
                        layer_color_link,
                    )

        # nf_links: addr → new_func (functions newly discovered at this layer)
        if next_new_funcs:
            nf_iv = iv_df[iv_df["function_name"].isin(next_new_funcs)]
            if len(nf_iv) > 0:
                nf_links = (nf_iv
                            .groupby(["ptr", "function_name", "resource_type"])
                            .size().reset_index(name="count"))
                nf_links = nf_links[nf_links["count"] > 0]

                for _, row in nf_links.iterrows():
                    ptr_key = f"addr:{row['ptr']}"
                    func_key = f"func:{row['function_name']}"
                    rt = row["resource_type"]
                    _add_node(ptr_key, f"{rt}:{row['ptr'][-8:]}", layer_color_node)
                    _add_node(func_key, row["function_name"], layer_color_node)
                    _add_link(
                        node_index[ptr_key],
                        node_index[func_key],
                        int(row["count"]),
                        layer_color_link,
                    )

                # new_func → thread links
                nf_threads = (nf_iv
                    .groupby(["function_name", "thread_label"])
                    .size().reset_index(name="count"))
                nf_threads = nf_threads[nf_threads["count"] > 0]

                for _, row in nf_threads.iterrows():
                    func_key = f"func:{row['function_name']}"
                    thread_key = f"thread:{row['thread_label']}"
                    _add_node(func_key, row["function_name"], layer_color_node)
                    _add_node(thread_key, f"T{row['thread_label']}", layer_color_node)
                    _add_link(
                        node_index[func_key],
                        node_index[thread_key],
                        int(row["count"]),
                        layer_color_link,
                    )

    # ── Compute per-(func, thread) WAIT durations for shared table ──
    if _duration_frames:
        _all_iv = pd.concat(_duration_frames, ignore_index=True)
        _all_iv["duration"] = _all_iv["end"] - _all_iv["start"]
        _ft_dur = _all_iv.groupby(
            ["function_name", "thread_label"])["duration"].sum()
    else:
        _ft_dur = pd.Series(dtype=float)

    # ── Build node type mapping for hover highlighting ──────────────
    node_types_raw = [""] * len(all_labels)
    for key, idx in node_index.items():
        if key.startswith("addr:"):
            node_types_raw[idx] = "addr"
        elif key.startswith("func:"):
            node_types_raw[idx] = "func"
        elif key.startswith("thread:"):
            node_types_raw[idx] = "thread"

    # ── Post-BFS: filter nodes by minimum flow ────────────────────────
    node_types = node_types_raw
    old_to_new = None  # set by min_flow filtering; None = identity mapping
    surviving_old_indices = None  # set after min_flow filtering

    if not sources:
        return _empty_fig(f"No significant relationships for {clicked_rt}"), set(), set()

    if min_flow and min_flow > 0:
        # Compute flow count per node (number of incoming + outgoing links)
        n_nodes = len(all_labels)
        node_flow = [0] * n_nodes
        for i in range(len(sources)):
            node_flow[sources[i]] += 1
            node_flow[targets[i]] += 1

        # Identify nodes to keep
        keep = set(i for i in range(n_nodes) if node_flow[i] >= min_flow)

        if not keep:
            return _empty_fig(f"All nodes below min flow {min_flow}"), set(), set()

        # Filter links: both endpoints must survive
        new_sources, new_targets, new_values, new_link_colors = [], [], [], []
        for i in range(len(sources)):
            if sources[i] in keep and targets[i] in keep:
                new_sources.append(sources[i])
                new_targets.append(targets[i])
                new_values.append(values[i])
                new_link_colors.append(link_colors[i])

        if not new_sources:
            return _empty_fig(f"No links remain after min flow filter ({min_flow})"), set(), set()

        # Re-index: build old->new mapping for surviving nodes
        # Also collect only nodes that still have links
        used = set(new_sources) | set(new_targets)
        surviving_old_indices = used
        old_to_new = {}
        filtered_labels = []
        filtered_colors = []
        filtered_node_types = []
        for old_idx in sorted(used):
            old_to_new[old_idx] = len(filtered_labels)
            filtered_labels.append(all_labels[old_idx])
            filtered_colors.append(all_colors[old_idx])
            filtered_node_types.append(node_types_raw[old_idx])

        sources = [old_to_new[s] for s in new_sources]
        targets = [old_to_new[t] for t in new_targets]
        values = new_values
        link_colors = new_link_colors
        all_labels = filtered_labels
        all_colors = filtered_colors
        node_types = filtered_node_types

    # ── Extract surviving entities for heatmap ────────────────────────
    idx_to_key = {v: k for k, v in node_index.items()}
    if surviving_old_indices is None:
        surviving_old_indices = set(range(len(idx_to_key)))
    sankey_ptrs = set()
    sankey_threads = set()
    for old_idx in surviving_old_indices:
        key = idx_to_key.get(old_idx, "")
        if key.startswith("addr:"):
            sankey_ptrs.add(key[5:])
        elif key.startswith("thread:"):
            sankey_threads.add(key[7:])

    # ── Build func-thread duration mapping for shared table ────────────
    func_thread_durations = {}
    for (func_name, thread_label), dur_ns in _ft_dur.items():
        func_key = f"func:{func_name}"
        thread_key = f"thread:{thread_label}"
        if func_key not in node_index or thread_key not in node_index:
            continue
        old_fi = node_index[func_key]
        old_ti = node_index[thread_key]
        if old_fi not in surviving_old_indices or old_ti not in surviving_old_indices:
            continue
        new_fi = old_to_new[old_fi] if old_to_new else old_fi
        new_ti = old_to_new[old_ti] if old_to_new else old_ti
        func_thread_durations.setdefault(
            str(new_fi), {})[str(new_ti)] = float(dur_ns)

    # ── Build trace-grounded triple maps for click-highlight ──────────
    # Bug fix: previously the clientside click handler decided whether
    # an address was "shared" between two threads by graph-walking the
    # Sankey topology (addr → any func → any thread).  The Sankey is
    # built from independent groupby aggregations that drop the joint
    # (ptr, function, thread) identity, so reachability there does NOT
    # imply real trace co-occurrence.  We compute the truth here from
    # the same data used to build the diagram and ship it via fig
    # meta so the JS handler can consult it directly.
    #
    # addr_thread_funcs[str(addr_idx)][str(thread_idx)] = [func_idx, ...]
    #     — for each surviving addr node, the funcs that the trace
    #       actually shows reaching each thread on that addr.
    # triple_link_map[str(addr_idx)+"|"+str(func_idx)+"|"+str(thread_idx)]
    #     = [link_idx_addr_func, link_idx_func_thread]
    #     — exact link indices to highlight for a given real triple.
    # addr_func_thread_durations[str(addr_idx)][str(func_idx)][str(thread_idx)]
    #     = ns — WAIT duration for this exact triple, summed only over
    #     intervals belonging to (ptr, func, thread).  Used to populate
    #     the Shared Contention Functions table restricted to truly
    #     shared addresses.
    addr_thread_funcs = {}
    triple_link_map = {}
    addr_func_thread_durations = {}

    def _new_idx(old_idx):
        if old_idx not in surviving_old_indices:
            return None
        return old_to_new[old_idx] if old_to_new else old_idx

    # Index links by (src, tgt) for fast lookup of the surviving links
    link_by_pair = {}
    for li in range(len(sources)):
        link_by_pair[(sources[li], targets[li])] = li

    # Collect all real (ptr, function, thread) triples used to build the
    # diagram.  WAIT-pair triples (layer 0 + new_func at layer >= 1):
    # take from _duration_frames.  Raw-event triples (expand_func at
    # layer >= 1): take from _trace_triple_frames.  Drop duplicates.
    _triple_frames = []
    for fr in _duration_frames:
        if len(fr) == 0:
            continue
        _triple_frames.append(
            fr[["ptr", "function_name", "thread_label"]])
    for fr in _trace_triple_frames:
        if len(fr) == 0:
            continue
        _triple_frames.append(fr)

    if _triple_frames:
        all_triples = (pd.concat(_triple_frames, ignore_index=True)
                       .drop_duplicates())
        for _, row in all_triples.iterrows():
            ptr = row["ptr"]
            fn = row["function_name"]
            tl = row["thread_label"]
            ak = f"addr:{ptr}"
            fk = f"func:{fn}"
            tk = f"thread:{tl}"
            if ak not in node_index or fk not in node_index \
                    or tk not in node_index:
                continue
            new_a = _new_idx(node_index[ak])
            new_f = _new_idx(node_index[fk])
            new_t = _new_idx(node_index[tk])
            if new_a is None or new_f is None or new_t is None:
                continue
            # Both edges (addr→func, func→thread) must survive in the
            # final Sankey for the triple to be highlightable.
            li_af = link_by_pair.get((new_a, new_f))
            li_ft = link_by_pair.get((new_f, new_t))
            if li_af is None or li_ft is None:
                continue
            ak_s, fk_s, tk_s = str(new_a), str(new_f), str(new_t)
            funcs_for_thread = (addr_thread_funcs
                                .setdefault(ak_s, {})
                                .setdefault(tk_s, []))
            if new_f not in funcs_for_thread:
                funcs_for_thread.append(new_f)
            triple_link_map[f"{ak_s}|{fk_s}|{tk_s}"] = [li_af, li_ft]

    # Per-(addr, func, thread) WAIT durations for the shared table —
    # restricted to triples that exist in WAIT intervals (not raw
    # events; raw-event triples have no duration).
    if _duration_frames:
        _all_iv_full = pd.concat(_duration_frames, ignore_index=True)
        if len(_all_iv_full) > 0:
            _all_iv_full = _all_iv_full.copy()
            _all_iv_full["duration"] = (_all_iv_full["end"]
                                         - _all_iv_full["start"])
            _aft = _all_iv_full.groupby(
                ["ptr", "function_name", "thread_label"]
            )["duration"].sum()
            for (ptr, fn, tl), dur_ns in _aft.items():
                ak = f"addr:{ptr}"
                fk = f"func:{fn}"
                tk = f"thread:{tl}"
                if ak not in node_index or fk not in node_index \
                        or tk not in node_index:
                    continue
                new_a = _new_idx(node_index[ak])
                new_f = _new_idx(node_index[fk])
                new_t = _new_idx(node_index[tk])
                if new_a is None or new_f is None or new_t is None:
                    continue
                (addr_func_thread_durations
                 .setdefault(str(new_a), {})
                 .setdefault(str(new_f), {})[str(new_t)]) = float(dur_ns)

    # ── Build the Sankey figure ─────────────────────────────────────────
    fig = go.Figure(go.Sankey(
        arrangement="fixed",
        valueformat="d",
        valuesuffix=" pairs",
        node=dict(
            pad=15, thickness=20,
            label=all_labels,
            color=all_colors,
        ),
        link=dict(
            source=sources, target=targets, value=values,
            color=link_colors,
        ),
    ))

    title_text = clicked_rt
    if max_depth > 0:
        title_text += f" (+{max_depth} layer{'s' if max_depth > 1 else ''})"

    fig.update_layout(
        title=dict(text=title_text, font=dict(size=14)),
        margin=dict(l=20, r=20, t=40, b=20),
        height=max(400, len(all_labels) * 20 + 100),
        meta=dict(
            node_types=node_types,
            sources=sources,
            targets=targets,
            default_link_colors=link_colors,
            default_node_colors=all_colors,
            func_thread_durations=func_thread_durations,
            addr_thread_funcs=addr_thread_funcs,
            triple_link_map=triple_link_map,
            addr_func_thread_durations=addr_func_thread_durations,
            time_divisor=_time_divisor(time_unit),
            time_label=_time_label(time_unit),
        ),
    )
    return fig, sankey_ptrs, sankey_threads


def _build_sankey_heatmap(full_df, sankey_ptrs, sankey_threads, n_bins,
                          time_unit):
    """Build a per-thread WAIT duration heatmap for Sankey entities.

    Filters WAIT intervals to addresses and threads that appear in the
    Sankey diagram.  Merges overlapping intervals per thread, then
    spreads wall-time duration into time bins.

    Returns a go.Figure (heatmap).
    """
    if not sankey_ptrs or not sankey_threads:
        return _empty_fig("No Sankey entities to display")

    ptr_df = full_df[full_df["ptr"].isin(sankey_ptrs)]
    intervals = _compute_wait_intervals(ptr_df)
    if not intervals:
        return _empty_fig("No WAIT pairs for Sankey addresses")

    divisor = _time_divisor(time_unit)
    tlabel = _time_label(time_unit)
    if n_bins is None:
        n_bins = 100

    # Filter intervals to Sankey threads and convert to display units
    intervals = [iv for iv in intervals
                 if iv["thread_label"] in sankey_threads]
    if not intervals:
        return _empty_fig("No WAIT pairs for Sankey threads")

    for iv in intervals:
        iv["start_disp"] = iv["start"] / divisor
        iv["end_disp"] = iv["end"] / divisor

    # Merge overlapping intervals per thread
    thread_labels = sorted(set(iv["thread_label"] for iv in intervals),
                           key=int)
    thread_idx_map = {t: i for i, t in enumerate(thread_labels)}

    from collections import defaultdict
    thread_ivs = defaultdict(list)
    for iv in intervals:
        thread_ivs[iv["thread_label"]].append(
            (iv["start_disp"], iv["end_disp"]))

    merged_ivs = []
    for tl in thread_labels:
        ivs = sorted(thread_ivs[tl], key=lambda x: x[0])
        if not ivs:
            continue
        cur_start, cur_end = ivs[0]
        for s, e in ivs[1:]:
            if s <= cur_end:
                cur_end = max(cur_end, e)
            else:
                merged_ivs.append((tl, cur_start, cur_end))
                cur_start, cur_end = s, e
        merged_ivs.append((tl, cur_start, cur_end))

    if not merged_ivs:
        return _empty_fig("No WAIT intervals after merging")

    all_starts = [iv[1] for iv in merged_ivs]
    all_ends = [iv[2] for iv in merged_ivs]
    t_min = min(all_starts)
    t_max = max(all_ends)
    if t_max <= t_min:
        return _empty_fig("All WAIT intervals at same time")

    bin_edges = np.linspace(t_min, t_max, n_bins + 1)
    matrix = np.zeros((len(thread_labels), n_bins), dtype=float)

    for tl, iv_start, iv_end in merged_ivs:
        row = thread_idx_map[tl]
        start_bin = max(0,
                        np.searchsorted(bin_edges, iv_start, side="right") - 1)
        end_bin = min(n_bins - 1,
                      np.searchsorted(bin_edges, iv_end, side="right") - 1)
        for b in range(start_bin, end_bin + 1):
            overlap = min(iv_end, bin_edges[b + 1]) - max(iv_start,
                                                           bin_edges[b])
            if overlap > 0:
                matrix[row, b] += overlap

    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    fig = go.Figure(go.Heatmap(
        z=matrix,
        x=bin_centers,
        y=thread_labels,
        colorscale=[[0, "#ffffff"], [1, "#8b0000"]],
        hovertemplate=(
            "Thread: %{y}<br>"
            f"Time: %{{x:.4g}} {tlabel}<br>"
            f"WAIT Duration: %{{z:.4g}} {tlabel}<br>"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        xaxis_title=f"Time ({tlabel}, relative)",
        yaxis_title="Thread",
        margin=dict(l=60, r=20, t=20, b=40),
        yaxis=dict(type="category", categoryorder="array",
                   categoryarray=thread_labels),
        height=max(300, len(thread_labels) * 30 + 100),
    )
    return fig


def register_bottleneck_callbacks(app):
    # ── Callback 1: update controls ──────────────────────────────────────
    @app.callback(
        Output("bottleneck-resource-dropdown", "options"),
        Output("bottleneck-thread-dropdown", "options"),
        Output("bottleneck-time-range", "min"),
        Output("bottleneck-time-range", "max"),
        Output("bottleneck-time-range", "value"),
        Output("bottleneck-time-range", "step"),
        Output("bottleneck-time-range", "marks"),
        Output("bottleneck-time-label", "children"),
        Input("data-store", "data"),
        Input("time-unit-toggle", "value"),
    )
    def update_controls(store_data, time_unit):
        tlabel = _time_label(time_unit)
        if not store_data or not store_data.get("loaded"):
            return [], [], 0, 1, [0, 1], 0.1, {}, f"Time Window ({tlabel}, relative)"
        resources = [{"label": r, "value": r} for r in sorted(store_data["resource_types"])]
        threads = [{"label": t, "value": t} for t in store_data["thread_labels"]]

        divisor = _time_divisor(time_unit)
        duration = (store_data["time_range_ns"][1] - store_data["time_range_ns"][0]) / divisor
        duration_r = round(duration, 4)
        step = max(0.0001, round(duration / 1000, 4))
        marks = {
            0: "0",
            duration_r: f"{duration_r:.4g}",
        }
        return (resources, threads, 0, duration_r, [0, duration_r], step, marks,
                f"Time Window ({tlabel}, relative)")

    # ── Callback 2a: update resource type bar ───────────────────────────
    @app.callback(
        Output("bottleneck-restype-bar", "figure"),
        Input("data-store", "data"),
        Input("bottleneck-resource-dropdown", "value"),
        Input("bottleneck-thread-dropdown", "value"),
        Input("bottleneck-time-range", "value"),
        Input("time-unit-toggle", "value"),
        Input("filtered-data-version", "data"),
    )
    def update_restype_bar(store_data, resource_filter, thread_filter,
                           time_range, time_unit, _fv):
        if not store_data or not store_data.get("loaded"):
            return _empty_fig("Load data to see bottleneck analysis")

        df = _get_df(store_data)
        if df is None:
            return _empty_fig("No data in cache")

        df = _apply_time_filter(df, time_range, time_unit)
        if resource_filter:
            df = df[df["resource_type"] == resource_filter]
        if thread_filter:
            df = df[df["thread_label"] == thread_filter]

        # Need WAIT events
        wait_events = df[df["has_wait"]]
        if len(wait_events) == 0:
            return _empty_fig("No WAIT events match filters")

        # ── Resource type bar chart ──
        restype_stats = wait_events.groupby("resource_type").agg(
            wait_count=("resource_type", "size"),
            unique_ptrs=("ptr", "nunique"),
        ).reset_index()
        restype_stats["ratio"] = (restype_stats["wait_count"] /
                                  restype_stats["unique_ptrs"]).round(1)
        restype_stats = restype_stats.sort_values("ratio", ascending=False)

        restype_fig = go.Figure(go.Bar(
            x=restype_stats["resource_type"],
            y=restype_stats["ratio"],
            marker_color="#e74c3c",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "WAIT/Addr Ratio: %{y:.1f}<br>"
                "WAIT Count: %{customdata[0]}<br>"
                "Unique Addresses: %{customdata[1]}<br>"
                "<extra></extra>"
            ),
            customdata=list(zip(restype_stats["wait_count"],
                                restype_stats["unique_ptrs"])),
        ))
        restype_fig.update_layout(
            xaxis_title="Resource Type",
            yaxis_title="WAIT / Addr Ratio",
            xaxis=dict(categoryorder="array",
                       categoryarray=restype_stats["resource_type"].tolist()),
            margin=dict(l=40, r=20, t=20, b=40),
        )

        return restype_fig

    # ── Callback 2b: update address bar on restype bar click ─────────────
    @app.callback(
        Output("bottleneck-addr-bar", "figure"),
        Input("bottleneck-restype-bar", "clickData"),
        Input("data-store", "data"),
        Input("bottleneck-resource-dropdown", "value"),
        Input("bottleneck-thread-dropdown", "value"),
        Input("bottleneck-time-range", "value"),
        Input("time-unit-toggle", "value"),
        Input("filtered-data-version", "data"),
    )
    def update_addr_bar(click_data, store_data, resource_filter, thread_filter,
                        time_range, time_unit, _fv):
        if not click_data:
            return _empty_fig("Click a resource type bar on the left to see its addresses")

        if not store_data or not store_data.get("loaded"):
            return _empty_fig("Load data to see bottleneck analysis")

        # Extract clicked resource type
        clicked_rt = click_data["points"][0]["x"]

        df = _get_df(store_data)
        if df is None:
            return _empty_fig("No data in cache")

        df = _apply_time_filter(df, time_range, time_unit)
        if resource_filter:
            df = df[df["resource_type"] == resource_filter]
        if thread_filter:
            df = df[df["thread_label"] == thread_filter]

        # Filter to the clicked resource type
        df = df[df["resource_type"] == clicked_rt]

        intervals = _compute_wait_intervals(df)
        if not intervals:
            return _empty_fig(f"No WAIT pairs for {clicked_rt}")

        iv_df = pd.DataFrame(intervals)
        iv_df["duration_ns"] = iv_df["end"] - iv_df["start"]
        divisor = _time_divisor(time_unit)
        tlabel = _time_label(time_unit)

        # Top 15 addresses for this resource type, ranked by total duration descending
        addr_dur = iv_df.groupby("ptr").agg(
            total_duration=("duration_ns", "sum"),
        ).sort_values("total_duration", ascending=False).head(15).reset_index()

        addr_dur["display_duration"] = addr_dur["total_duration"] / divisor
        addr_dur["ptr_short"] = addr_dur["ptr"].str[-8:]

        addr_fig = go.Figure(go.Bar(
            y=addr_dur["ptr_short"],
            x=addr_dur["display_duration"],
            orientation="h",
            marker_color="#e74c3c",
            hovertemplate=(
                "<b>%{customdata}</b><br>"
                f"Resource: {clicked_rt}<br>"
                f"Total WAIT Duration: %{{x:.4g}} {tlabel}<br>"
                "<extra></extra>"
            ),
            customdata=addr_dur["ptr"],
        ))
        addr_fig.update_layout(
            title=dict(text=clicked_rt, font=dict(size=14)),
            xaxis_title=f"Total WAIT Duration ({tlabel})",
            yaxis_title="Address",
            margin=dict(l=100, r=20, t=30, b=40),
            yaxis=dict(categoryorder="total ascending"),
            height=max(300, len(addr_dur) * 22 + 100),
        )
        return addr_fig

    # ── Callback 3: cascading contention Sankey + temporal heatmap ──────
    @app.callback(
        Output("bottleneck-cascade-sankey", "figure"),
        Output("bottleneck-temporal-heatmap", "figure"),
        Input("bottleneck-restype-bar", "clickData"),
        Input("data-store", "data"),
        Input("bottleneck-resource-dropdown", "value"),
        Input("bottleneck-thread-dropdown", "value"),
        Input("bottleneck-time-range", "value"),
        Input("bottleneck-bins-slider", "value"),
        Input("time-unit-toggle", "value"),
        Input("filtered-data-version", "data"),
        Input("bottleneck-cascade-depth", "value"),
        Input("bottleneck-cascade-explore-0", "value"),
        Input("bottleneck-cascade-explore-1", "value"),
        Input("bottleneck-cascade-explore-2", "value"),
        Input("bottleneck-cascade-explore-3", "value"),
        Input("bottleneck-cascade-display-0", "value"),
        Input("bottleneck-cascade-display-1", "value"),
        Input("bottleneck-cascade-display-2", "value"),
        Input("bottleneck-cascade-display-3", "value"),
        Input("bottleneck-cascade-min-flow", "value"),
    )
    def update_cascade(click_data, store_data, resource_filter, thread_filter,
                       time_range, n_bins, time_unit, _fv, max_depth,
                       exp0, exp1, exp2, exp3,
                       disp0, disp1, disp2, disp3, min_flow):
        empty_heatmap = _empty_fig(
            "Click a resource type bar to see temporal contention")
        if not click_data:
            return (_empty_fig("Click a resource type bar to see its "
                               "address → function → thread flow"),
                    empty_heatmap)

        if not store_data or not store_data.get("loaded"):
            return (_empty_fig("Load data to see cascading contention"),
                    empty_heatmap)

        clicked_rt = click_data["points"][0]["x"]

        df = _get_df(store_data)
        if df is None:
            return _empty_fig("No data in cache"), empty_heatmap

        df = _apply_time_filter(df, time_range, time_unit)
        if resource_filter:
            df = df[df["resource_type"] == resource_filter]
        if thread_filter:
            df = df[df["thread_label"] == thread_filter]

        if max_depth is None:
            max_depth = 0
        explore_limits = [exp0 or 15, exp1 or 10, exp2 or 5, exp3 or 5]
        display_limits = [disp0 or 15, disp1 or 10, disp2 or 5, disp3 or 5]

        sankey_fig, sankey_ptrs, sankey_threads = _build_cascade_sankey(
            df, clicked_rt, max_depth, explore_limits, display_limits,
            min_flow=min_flow or 0, time_unit=time_unit)

        heatmap_fig = _build_sankey_heatmap(
            df, sankey_ptrs, sankey_threads, n_bins, time_unit)

        return sankey_fig, heatmap_fig

    # ── Callback 4: toggle layer slider visibility ─────────────────────
    @app.callback(
        Output("bottleneck-cascade-row-0", "style"),
        Output("bottleneck-cascade-row-1", "style"),
        Output("bottleneck-cascade-row-2", "style"),
        Output("bottleneck-cascade-row-3", "style"),
        Input("bottleneck-cascade-depth", "value"),
    )
    def toggle_layer_sliders(depth):
        if depth is None:
            depth = 0
        row_style_visible = {"display": "flex", "alignItems": "center",
                             "gap": "4px", "marginBottom": "4px"}
        row_style_hidden = {"display": "none", "alignItems": "center",
                            "gap": "4px", "marginBottom": "4px"}
        return tuple(
            row_style_visible if i <= depth else row_style_hidden
            for i in range(4)
        )

    # ── Clientside callback: node hover + click highlighting ────────
    app.clientside_callback(
        """
        function(figure) {
            if (window._sankeySetupTimeout) {
                clearTimeout(window._sankeySetupTimeout);
            }

            function setupHandlers() {
                var plotlyDiv = document.querySelector(
                    '#bottleneck-cascade-sankey .js-plotly-plot');
                if (!plotlyDiv || !plotlyDiv.data) {
                    window._sankeySetupTimeout = setTimeout(
                        setupHandlers, 200);
                    return;
                }

                if (!figure || !figure.layout || !figure.layout.meta) return;
                var meta = figure.layout.meta;
                if (!meta.sources || !meta.node_types
                        || !meta.default_link_colors
                        || !meta.default_node_colors) return;

                // Remove previous listeners
                if (plotlyDiv._nodeHoverHandler) {
                    plotlyDiv.removeListener(
                        'plotly_hover', plotlyDiv._nodeHoverHandler);
                    plotlyDiv.removeListener(
                        'plotly_unhover', plotlyDiv._nodeUnhoverHandler);
                }
                if (plotlyDiv._nodeClickHandler) {
                    plotlyDiv.removeListener(
                        'plotly_click', plotlyDiv._nodeClickHandler);
                }

                // Reset click state on new figure
                plotlyDiv._threadSelection = [];
                plotlyDiv._clickHighlightActive = false;
                var tableDiv = document.getElementById(
                    'bottleneck-shared-table');
                if (tableDiv) tableDiv.innerHTML = '';

                // ── Hover handler ───────────────────────────────
                // Bug fix: highlight is grounded in real trace
                // (ptr, function, thread) triples shipped via
                // meta.addr_thread_funcs / meta.triple_link_map,
                // NOT Sankey graph reachability.  Otherwise hovering
                // an addr would light up threads that never touched
                // it (just because they share a function with it on
                // a different addr), and hovering a thread would
                // light up addrs the thread never reached (just
                // because they share a function with addrs the
                // thread did reach).
                plotlyDiv._nodeHoverHandler = function(data) {
                    // Suppress hover while click-highlight is active
                    if (plotlyDiv._clickHighlightActive) return;
                    if (!data || !data.points || !data.points.length) return;
                    var pt = data.points[0];
                    if (pt.source !== undefined
                            && typeof pt.source === 'object') return;
                    var nodeIdx = pt.pointNumber;
                    var nodeType = (nodeIdx !== undefined)
                        ? meta.node_types[nodeIdx] : null;
                    if (!nodeType) {
                        Plotly.restyle(plotlyDiv,
                            {'link.color': [meta.default_link_colors]}, [0]);
                        return;
                    }

                    var highlightLinks = new Set();
                    var atfMap = meta.addr_thread_funcs || {};
                    var tlMap = meta.triple_link_map || {};

                    if (nodeType === 'addr') {
                        // Only highlight (addr→func, func→thread) link
                        // pairs that come from REAL trace triples on
                        // this addr.
                        var aKey = String(nodeIdx);
                        var byThread = atfMap[aKey] || {};
                        for (var tStr in byThread) {
                            if (!byThread.hasOwnProperty(tStr)) continue;
                            var funcs = byThread[tStr];
                            for (var k = 0; k < funcs.length; k++) {
                                var triKey = aKey + '|'
                                    + String(funcs[k]) + '|' + tStr;
                                var lnks = tlMap[triKey];
                                if (!lnks) continue;
                                for (var m = 0; m < lnks.length; m++) {
                                    highlightLinks.add(lnks[m]);
                                }
                            }
                        }
                    } else if (nodeType === 'func') {
                        // Func hover: highlight links whose endpoint
                        // IS this func.  This is already trace-true
                        // (no transitive reachability).
                        for (var i = 0; i < meta.targets.length; i++) {
                            if (meta.targets[i] === nodeIdx) {
                                highlightLinks.add(i);
                            }
                        }
                        for (var i = 0; i < meta.sources.length; i++) {
                            if (meta.sources[i] === nodeIdx) {
                                highlightLinks.add(i);
                            }
                        }
                    } else {
                        // Thread hover: only highlight (addr→func,
                        // func→thread) link pairs that come from
                        // REAL trace triples reaching THIS thread.
                        var tKey = String(nodeIdx);
                        for (var aStr in atfMap) {
                            if (!atfMap.hasOwnProperty(aStr)) continue;
                            var byT = atfMap[aStr];
                            var funcs = byT[tKey];
                            if (!funcs || !funcs.length) continue;
                            for (var k = 0; k < funcs.length; k++) {
                                var triKey = aStr + '|'
                                    + String(funcs[k]) + '|' + tKey;
                                var lnks = tlMap[triKey];
                                if (!lnks) continue;
                                for (var m = 0; m < lnks.length; m++) {
                                    highlightLinks.add(lnks[m]);
                                }
                            }
                        }
                    }

                    var newColors = meta.default_link_colors.slice();
                    for (var i = 0; i < newColors.length; i++) {
                        newColors[i] = highlightLinks.has(i)
                            ? 'rgba(255, 0, 0, 0.7)'
                            : 'rgba(200, 200, 200, 0.1)';
                    }
                    Plotly.restyle(plotlyDiv,
                        {'link.color': [newColors]}, [0]);
                };

                plotlyDiv._nodeUnhoverHandler = function(data) {
                    if (plotlyDiv._clickHighlightActive) return;
                    Plotly.restyle(plotlyDiv,
                        {'link.color': [meta.default_link_colors]}, [0]);
                };

                // ── Click handler (thread-pair highlighting) ────
                plotlyDiv._nodeClickHandler = function(data) {
                    if (!data || !data.points || !data.points.length) return;
                    var pt = data.points[0];
                    // Skip link clicks
                    if (pt.source !== undefined
                            && typeof pt.source === 'object') return;
                    var nodeIdx = pt.pointNumber;
                    if (nodeIdx === undefined
                            || meta.node_types[nodeIdx] !== 'thread') return;

                    // Ignore if already selected
                    var sel = plotlyDiv._threadSelection;
                    if (sel.indexOf(nodeIdx) !== -1) return;

                    sel.push(nodeIdx);
                    if (sel.length > 2) sel.shift();

                    if (sel.length === 1) {
                        // One thread selected — highlight just this node
                        var nc = meta.default_node_colors.slice();
                        nc[sel[0]] = 'rgba(255, 0, 0, 1)';
                        Plotly.restyle(plotlyDiv, {
                            'node.color': [nc],
                            'link.color': [meta.default_link_colors]
                        }, [0]);
                        plotlyDiv._clickHighlightActive = true;
                        return;
                    }

                    // Two threads selected — shared contention analysis
                    // Bug fix: highlight is grounded in real trace
                    // (ptr, function, thread) triples shipped via
                    // meta.addr_thread_funcs / meta.triple_link_map,
                    // NOT in Sankey graph reachability.  Otherwise an
                    // address only touched by T1 (through some func F)
                    // would be falsely flagged as shared with T2 just
                    // because F also reached T2 on a different addr.
                    var T1 = sel[0], T2 = sel[1];
                    var highlightNodes = new Set([T1, T2]);
                    var highlightLinks = new Set();
                    var sharedAddrs = [];           // [addr_idx, ...]
                    // sharedFuncsByThread[T1] = Set(func_idx) of funcs
                    // whose real (addr, func, T1) triple participates
                    // in the shared contention; same for T2.
                    var sharedFuncsByThread = {};
                    sharedFuncsByThread[T1] = new Set();
                    sharedFuncsByThread[T2] = new Set();
                    // sharedFuncAddrsByThread[T1][f] = Set(addr_idx)
                    // of shared addresses that link f → T1 in the trace.
                    var sharedFuncAddrsByThread = {};
                    sharedFuncAddrsByThread[T1] = {};
                    sharedFuncAddrsByThread[T2] = {};

                    var atfMap = meta.addr_thread_funcs || {};
                    var tlMap = meta.triple_link_map || {};
                    var t1Key = String(T1), t2Key = String(T2);

                    for (var a = 0; a < meta.node_types.length; a++) {
                        if (meta.node_types[a] !== 'addr') continue;
                        var aKey = String(a);
                        var atf = atfMap[aKey];
                        if (!atf) continue;
                        var fT1 = atf[t1Key];
                        var fT2 = atf[t2Key];
                        if (!fT1 || !fT2
                                || !fT1.length || !fT2.length) continue;

                        // Real shared address — only highlight funcs
                        // and links that come from genuine triples.
                        sharedAddrs.push(a);
                        highlightNodes.add(a);

                        function _processSide(threadIdx, funcs) {
                            for (var k = 0; k < funcs.length; k++) {
                                var f = funcs[k];
                                var triKey = aKey + '|' + String(f)
                                    + '|' + String(threadIdx);
                                var lnks = tlMap[triKey];
                                if (!lnks) continue;
                                highlightNodes.add(f);
                                sharedFuncsByThread[threadIdx].add(f);
                                var fa = sharedFuncAddrsByThread[
                                    threadIdx];
                                if (!fa[f]) fa[f] = new Set();
                                fa[f].add(a);
                                for (var m = 0; m < lnks.length; m++) {
                                    highlightLinks.add(lnks[m]);
                                }
                            }
                        }
                        _processSide(T1, fT1);
                        _processSide(T2, fT2);
                    }

                    // Apply node + link colors
                    var nc = meta.default_node_colors.slice();
                    for (var i = 0; i < nc.length; i++) {
                        nc[i] = highlightNodes.has(i)
                            ? 'rgba(255, 0, 0, 1)'
                            : 'rgba(200, 200, 200, 0.3)';
                    }
                    var lc = meta.default_link_colors.slice();
                    for (var i = 0; i < lc.length; i++) {
                        lc[i] = highlightLinks.has(i)
                            ? 'rgba(255, 0, 0, 0.7)'
                            : 'rgba(200, 200, 200, 0.1)';
                    }
                    Plotly.restyle(plotlyDiv, {
                        'node.color': [nc],
                        'link.color': [lc]
                    }, [0]);
                    plotlyDiv._clickHighlightActive = true;

                    // Build shared contention table — durations are
                    // summed ONLY over the truly shared addresses for
                    // each (function, thread) pair, using the trace-
                    // grounded addr_func_thread_durations map.
                    var tableDiv = document.getElementById(
                        'bottleneck-shared-table');
                    if (tableDiv && meta.addr_func_thread_durations) {
                        var aftd = meta.addr_func_thread_durations;
                        var labels = plotlyDiv.data[0].node.label;
                        var dv = meta.time_divisor || 1e6;
                        var tl = meta.time_label || 'ms';

                        function _rowsFor(threadIdx) {
                            var fa = sharedFuncAddrsByThread[threadIdx];
                            var rows = [];
                            for (var fStr in fa) {
                                if (!fa.hasOwnProperty(fStr)) continue;
                                var f = parseInt(fStr, 10);
                                var addrSet = fa[fStr];
                                var totalNs = 0;
                                addrSet.forEach(function(a) {
                                    var byF = aftd[String(a)];
                                    if (!byF) return;
                                    var byT = byF[String(f)];
                                    if (!byT) return;
                                    var v = byT[String(threadIdx)];
                                    if (v) totalNs += v;
                                });
                                rows.push({
                                    n: labels[f],
                                    d: totalNs / dv
                                });
                            }
                            rows.sort(function(a, b) {
                                return b.d - a.d; });
                            return rows;
                        }
                        var t1F = _rowsFor(T1);
                        var t2F = _rowsFor(T2);
                        function mkTbl(lbl, rows) {
                            var h = '<h6 style="margin:8px 0 4px;">'
                                + lbl + '</h6>'
                                + '<table style="width:100%;'
                                + 'border-collapse:collapse;'
                                + 'font-size:13px;"><thead>'
                                + '<tr style="border-bottom:'
                                + '2px solid #333;">'
                                + '<th style="text-align:left;'
                                + 'padding:4px 8px;">Function</th>'
                                + '<th style="text-align:right;'
                                + 'padding:4px 8px;">WAIT Duration ('
                                + tl + ')</th></tr></thead><tbody>';
                            for (var i = 0; i < rows.length; i++) {
                                h += '<tr style="border-bottom:'
                                    + '1px solid #ddd;">'
                                    + '<td style="padding:4px 8px;'
                                    + 'word-break:break-all;">'
                                    + rows[i].n + '</td>'
                                    + '<td style="text-align:right;'
                                    + 'padding:4px 8px;'
                                    + 'white-space:nowrap;">'
                                    + rows[i].d.toFixed(4)
                                    + '</td></tr>';
                            }
                            if (!rows.length) {
                                h += '<tr><td colspan="2" style='
                                    + '"padding:4px 8px;color:#888;">'
                                    + 'No functions</td></tr>';
                            }
                            h += '</tbody></table>';
                            return h;
                        }
                        var th = '<h5 style="margin-bottom:8px;">'
                            + 'Shared Contention Functions</h5>';
                        th += mkTbl(labels[T1], t1F);
                        th += '<hr style="margin:12px 0;border:0;'
                            + 'border-top:2px solid #333;">';
                        th += mkTbl(labels[T2], t2F);
                        tableDiv.innerHTML = th;
                    }
                };

                plotlyDiv.on('plotly_hover', plotlyDiv._nodeHoverHandler);
                plotlyDiv.on('plotly_unhover', plotlyDiv._nodeUnhoverHandler);
                plotlyDiv.on('plotly_click', plotlyDiv._nodeClickHandler);
            }

            window._sankeySetupTimeout = setTimeout(setupHandlers, 300);
            return window.dash_clientside.no_update;
        }
        """,
        Output("bottleneck-hover-dummy", "children"),
        Input("bottleneck-cascade-sankey", "figure"),
    )

    # ── Clientside callback: reset thread selection ──────────────────
    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) return window.dash_clientside.no_update;
            var plotlyDiv = document.querySelector(
                '#bottleneck-cascade-sankey .js-plotly-plot');
            if (!plotlyDiv || !plotlyDiv.data) {
                return window.dash_clientside.no_update;
            }
            plotlyDiv._threadSelection = [];
            plotlyDiv._clickHighlightActive = false;
            var tableDiv = document.getElementById(
                'bottleneck-shared-table');
            if (tableDiv) tableDiv.innerHTML = '';
            var meta = plotlyDiv.layout && plotlyDiv.layout.meta;
            if (meta && meta.default_link_colors && meta.default_node_colors) {
                Plotly.restyle(plotlyDiv, {
                    'node.color': [meta.default_node_colors],
                    'link.color': [meta.default_link_colors]
                }, [0]);
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("bottleneck-hover-dummy", "style"),
        Input("bottleneck-cascade-reset", "n_clicks"),
    )