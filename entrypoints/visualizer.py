import os
import json

from abc import ABC, abstractmethod
from collections import namedtuple
from typing import Dict, List, Set, Union, Tuple, Callable, TypeVar
from enum import Enum

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

from dynamic_profiling.core import OperationType, load_instru_mapping, EventRecord, GlobalEventView


class SingleOperationHeatmapView:
	def __init__(self,
              	 global_event_view: GlobalEventView,
                 resource_name: str,
                 operation_type: OperationType,
              	 time_window_size: int):
		self.num_ticks = global_event_view.elapsed_time // time_window_size + 1
		self.brackets = np.zeros((global_event_view.num_threads, self.num_ticks), dtype=int)

		# Iterate through events and populate the heatmap
		for record in global_event_view.event_records:
			if record.resource_name == resource_name and record.op_type == operation_type:
				thread_idx = record.thread_id
				time_idx = record.timestamp // time_window_size
				self.brackets[thread_idx][time_idx] += 1

	@property
	def count(self) -> int:
		return np.sum(self.brackets)


class MultiOperationHeatmapView:
	def __init__(self,
              	 global_event_view: GlobalEventView,
                 resource_name: str,
              	 time_window_size: int):
		NUM_OPERATIONS = 4  # ACQUIRE, USE, WAIT, RELEASE
		self.num_ticks = global_event_view.elapsed_time // time_window_size + 1
		self.brackets = np.zeros((global_event_view.num_threads * NUM_OPERATIONS, self.num_ticks), dtype=int)

		# Iterate through events and populate the heatmap
		for record in global_event_view.event_records:
			if record.resource_name == resource_name:
				thread_idx = record.thread_id
				time_idx = record.timestamp // time_window_size
				self.brackets[thread_idx*NUM_OPERATIONS + record.op_type.value][time_idx] += 1

	def get_operation_heatmap(self, operation_type: OperationType) -> np.ndarray:
		# Get a copy with only the specified operation type's counts (others set to 0)
		NUM_OPERATIONS = 4
		op_brackets = np.zeros_like(self.brackets)
		op_brackets[operation_type.value::NUM_OPERATIONS, :] = self.brackets[operation_type.value::NUM_OPERATIONS, :]
		return op_brackets

	@property
	def count(self) -> int:
		return np.sum(self.brackets)


if __name__ == "__main__":
	res2pos_mapping_fp = "demo-case/MDL/outputs/omniprofiler/global_resource_mapping.json"
	res2func_mapping_fp = "demo-case/MDL/outputs/omniprofiler/global_function_mapping.json"
	profile_data_dir = "demo-case/MDL/outputs/omniprofiler/dynamic-profiling-data"
	
	verbose = False

	pos2res_mapping = load_instru_mapping(res2pos_mapping_fp)
	pos2func_mapping = load_instru_mapping(res2func_mapping_fp)
	global_event_view = GlobalEventView()
	global_event_view.load_dir(pos2res_mapping, pos2func_mapping, profile_data_dir)

	# 1s time window
	res_name = "MDL_context"
	multi_view_heatmap = MultiOperationHeatmapView(global_event_view, res_name, time_window_size=1_000_000_000)
	print(multi_view_heatmap.count)

	plt.figure(figsize=(12, 8))

	op_list = [OperationType.ACQUIRE, OperationType.USE, OperationType.WAIT, OperationType.RELEASE]
	color_map = {
		OperationType.ACQUIRE: "Blues",
		OperationType.USE: "Greens",
		OperationType.WAIT: "Reds",
		OperationType.RELEASE: "Greys"
	}
	for op in op_list:
		heatmap = multi_view_heatmap.get_operation_heatmap(op)
		print(f"Total {op.name} count for '{res_name}': {np.sum(heatmap)}")
  		# Add opacity when count is low to visually distinguish from zero-count cells
		heatmap = np.where(heatmap > 0, heatmap, np.nan)  # Use NaN for zero counts to make them transparent in the heatmap
		sns.heatmap(heatmap, cmap=color_map[op], cbar_kws={'label': f'Number of {op.name}'})

	# No y ticks, just solid horizontal lines to separate different threads
	plt.yticks([])
	for i in range(global_event_view.num_threads):
		plt.text(-0.5, i*len(op_list) + len(op_list)/2 - 0.5, f"Thread {i}", va='center', ha='right', fontsize=8)

	# solid horizontal lines to separate different threads
	for i in range(1, global_event_view.num_threads):
		plt.axhline(y=i*len(op_list), color='black', linestyle='-')

	skips = set()
	for idx, record in enumerate(global_event_view.event_records):
		if idx in skips:
			continue
		if record.resource_name == res_name and record.thread_id == 1:
			time_sec = record.timestamp / 1_000_000_000
			is_exit_str = "EXIT" if record.at_exit else "ENTER"

			if record.op_type == OperationType.WAIT:
				# Find associated ACQUIRE and RELEASE events for the same address and thread to determine the waiting duration
				associated_events_ops = []
				latest_peek_idx = idx
				
				for peek_idx in range(idx + 1, len(global_event_view.event_records)):
					peek_record = global_event_view.event_records[peek_idx]
					if (peek_record.thread_id == record.thread_id and
         				peek_record.addr == record.addr and
             			peek_record.resource_name == record.resource_name and
     					peek_record.function_name == record.function_name and 
          				peek_record.timestamp == record.timestamp and 
              			not peek_record.at_exit):
						associated_events_ops.append(peek_record.op_type)
						skips.add(peek_idx)
						latest_peek_idx = max(latest_peek_idx, peek_idx)
					else:
						break  # Stop peeking once we encounter a different event

				# Find the exit events
				duration = 0
				for peek_idx in range(latest_peek_idx + 1, len(global_event_view.event_records)):
					peek_record = global_event_view.event_records[peek_idx]
					if (peek_record.thread_id == record.thread_id and
		 				peek_record.addr == record.addr and
						peek_record.resource_name == record.resource_name and 
						peek_record.function_name == record.function_name and 
						peek_record.timestamp >= record.timestamp and 
						peek_record.op_type == OperationType.WAIT and
						peek_record.at_exit):
						duration = (peek_record.timestamp - record.timestamp) / 1_000_000  # Convert to ms
						for offset in range(len(associated_events_ops)+1):
							skips.add(peek_idx + offset)
						break
					else:
						continue  # Stop peeking once we encounter a different event

				if 30 < time_sec < 42:
					aggregate_ops = "+".join(["WAIT"] + [op.name for op in associated_events_ops]) if associated_events_ops else "WAIT"
					print(f"[{aggregate_ops} - {duration:.2f} ms] [{time_sec:.2f} s] [{record.function_name}] [{record.addr}]")
			else:
				if 30 < time_sec < 42:
					print(f"[{record.op_type.name}] [{time_sec:.2f} s] [{record.function_name}-{is_exit_str}] [{record.addr}]")

	plt.title(f"Heatmap of {res_name} Uses Over Time and Threads")
	plt.xlabel("Time Window (s)")
	plt.tight_layout()
	plt.show()



