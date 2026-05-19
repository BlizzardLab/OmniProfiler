#!/bin/bash

# export the function list
perf report -T -g none --no-children -n --header -i perf.data > function_list.txt

# Find the path to FlameGraph
FLAMEGRAPH_DIR=$(find ~/ -type d -name "FlameGraph" 2>/dev/null | head -n 1)

if [[ -z $FLAMEGRAPH_DIR ]]; then
    echo "FlameGraph directory not found, please manually set the path to FlameGraph"
    # abort
    exit 1
else
    echo "FlameGraph found: $FLAMEGRAPH_DIR"
fi

perf script | $FLAMEGRAPH_DIR/stackcollapse-perf.pl > out.perf-folded
cat out.perf-folded | $FLAMEGRAPH_DIR/flamegraph.pl > perf-kernel.svg
