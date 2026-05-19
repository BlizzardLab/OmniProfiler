"""Data ingestion module — loads profiling JSON files into a pandas DataFrame.

Responsibilities:
    - Read global_resource_mapping.json, global_function_mapping.json, and
      index.json to build lookup maps (resource names, demangled function names).
    - Parse all thread_*.json files from the dynamic-profiling-data/ subdirectory.
    - Assemble a unified DataFrame with columns: thread_id, process_id,
      resource_type, resource_type_idx, event, function_index, function_name,
      is_exit, ptr, ts_ns, ts_relative_ns, has_use, has_release, has_acquire,
      has_wait, has_end, has_access, has_get, thread_label.
    - Normalize timestamps to relative (start at 0).
    - Remap thread IDs to a 0-based integer index.
    - Split comma-separated event strings into boolean has_* columns.

Public functions:
    load_dataset(directory_path) -> dict

Used by:
    callbacks.data_callbacks (called on data load)

Protocol:
    Every edition on the code should be reflected (i.e., updated) in this
    header and also the CLAUDE.md under the same directory of this script,
    meanwhile check if there are any tasks required by the CLAUDE.md.
"""

import json
import os
import re

import pandas as pd


def load_dataset(directory_path: str) -> dict:
    """Load all profiling data from a directory.

    Returns a dict with keys:
        - 'df': pandas DataFrame of all events
        - 'resource_map': {name: index}
        - 'resource_map_rev': {index: name}
        - 'function_index_to_name': {index: demangled_name}
        - 'function_metadata': {mangled_name: {metadata + resource info}}
        - 'threads': list of (pid, tid) tuples
        - 'time_range_ns': (min_ts, max_ts) in original nanoseconds
    """
    directory_path = os.path.abspath(directory_path)

    # Load resource mapping
    with open(os.path.join(directory_path, "global_resource_mapping.json"), "r") as f:
        resource_map = json.load(f)
    resource_map_rev = {v: k for k, v in resource_map.items()}

    # Load function mapping (mangled -> index)
    with open(os.path.join(directory_path, "global_function_mapping.json"), "r") as f:
        function_map = json.load(f)

    # Load index.json for demangled names and metadata
    with open(os.path.join(directory_path, "index.json"), "r") as f:
        function_metadata = json.load(f)

    # Build index -> demangled name map
    function_index_to_name = {}
    for mangled_name, info in function_metadata.items():
        meta = info.get("__metadata__", {})
        idx = meta.get("function_index")
        demangled = meta.get("demangled_name", mangled_name)
        if idx is not None:
            function_index_to_name[idx] = demangled

    # Load thread files
    data_dir = os.path.join(directory_path, "dynamic-profiling-data")
    thread_pattern = re.compile(r"thread_(\d+)_(\d+)\.json$")

    all_events = []
    threads = []

    for filename in os.listdir(data_dir):
        m = thread_pattern.match(filename)
        if not m:
            continue
        pid, tid = int(m.group(1)), int(m.group(2))
        threads.append((pid, tid))

        filepath = os.path.join(data_dir, filename)
        with open(filepath, "r") as f:
            thread_data = json.load(f)

        raw_event_per_res_count = {}  # check if any ringbuffer overflow (raw events per resource type)
        for resource_type_idx_str, events in thread_data.items():
            resource_type_idx = int(resource_type_idx_str)
            raw_event_per_res_count[resource_type_idx] = len(events)
            resource_name = resource_map_rev.get(resource_type_idx, f"unknown_{resource_type_idx}")
            for ev in events:
                all_events.append({
                    "thread_id": tid,
                    "process_id": pid,
                    "resource_type": resource_name,
                    "resource_type_idx": resource_type_idx,
                    "event": ev["event"],
                    "function_index": ev["function_index"],
                    "function_name": function_index_to_name.get(ev["function_index"], f"func_{ev['function_index']}"),
                    "is_exit": ev["is_exit"],
                    "ptr": ev["ptr"],
                    "ts_ns": int(ev["ts_ns"]),
                })

        for res_idx, count in raw_event_per_res_count.items():
            if count > 16384:  # Arbitrary threshold to flag potential ringbuffer overflow
                print(f"Warning: Thread {tid} has {count} raw events for resource [{resource_map_rev.get(res_idx, 'unknown')}], indicating ringbuffer overflow.")

    if not all_events:
        df = pd.DataFrame(columns=[
            "thread_id", "process_id", "resource_type", "resource_type_idx",
            "event", "function_index", "function_name", "is_exit", "ptr", "ts_ns",
            "ts_relative_ns", "has_use", "has_release", "has_acquire", "has_wait",
            "has_access", "has_get", "has_end", "thread_label",
        ])
        return {
            "df": df,
            "resource_map": resource_map,
            "resource_map_rev": resource_map_rev,
            "function_index_to_name": function_index_to_name,
            "function_metadata": function_metadata,
            "threads": threads,
            "time_range_ns": (0, 0),
        }

    df = pd.DataFrame(all_events)
    df.sort_values("ts_ns", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Relative timestamps (start at 0)
    ts_min = df["ts_ns"].min()
    ts_max = df["ts_ns"].max()
    df["ts_relative_ns"] = df["ts_ns"] - ts_min

    # Boolean columns for event types (events can be comma-separated)
    for etype in ("USE", "RELEASE", "ACQUIRE", "WAIT", "ACCESS", "GET", "END"):
        df[f"has_{etype.lower()}"] = df["event"].str.contains(etype, regex=False, na=False)

    # Remap thread IDs to 0-based index (sorted by thread_id)
    sorted_tids = sorted(df["thread_id"].unique())
    tid_to_index = {tid: idx for idx, tid in enumerate(sorted_tids)}
    df["thread_label"] = df["thread_id"].map(tid_to_index).astype(str)

    threads.sort()

    return {
        "df": df,
        "resource_map": resource_map,
        "resource_map_rev": resource_map_rev,
        "function_index_to_name": function_index_to_name,
        "function_metadata": function_metadata,
        "threads": threads,
        "time_range_ns": (int(ts_min), int(ts_max)),
    }
