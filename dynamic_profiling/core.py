import os

from enum import Enum
from typing import List, Dict, Callable, Union, Set, Tuple
from collections import namedtuple

import json

### Utilities ###

class OperationType(Enum):
	UNDEFINED 	= -1     # undefined
	WAIT 		= 0     # wait happens
	ACQUIRE 	= 1     # acquire <resource>
	USE 		= 2     # use <resource>
	RELEASE 	= 3     # release <resource>

def str2oper(oper_str: str) -> List[OperationType]:
    # Here we make sure WAIT appears before other events
	ret = []
	if "WAIT" in oper_str:
		ret.append(OperationType.WAIT)
	if "ACQUIRE" in oper_str:
		ret.append(OperationType.ACQUIRE)
	if "USE" in oper_str:
		ret.append(OperationType.USE)
	if "RELEASE" in oper_str:
		ret.append(OperationType.RELEASE)

	return ret if len(ret) > 0 else [OperationType.UNDEFINED]

def load_instru_mapping(fp: Union[str, os.PathLike]) -> Dict[int, str]:
	vk_mapping = {}
	with open(fp, 'r') as f:
		kv_mapping = json.load(f)
	for res_name, pos in kv_mapping.items():
		vk_mapping[str(pos)] = res_name
	return vk_mapping

def load_resource_func(fp: Union[str, os.PathLike], filter: Set[str]) -> Dict[str, List[Tuple[str, OperationType]]]:
	with open(fp, 'r') as f:
		all_resource = json.load(f)

	# Dict[function_name -> List[Tuple[resource_name, operation_type]]]
	funcname2resource_dict: Dict[str, List[Tuple[str, OperationType]]] = {}

	for resource, operators in all_resource.items():
		for oper_type, oper_list in operators.items():
			intru_opers = set(oper_list) & filter
			for funcname in intru_opers:
				funcname2resource_dict.setdefault(funcname, []).append((resource, str2oper(oper_type)))
				print(funcname2resource_dict[funcname])

	return funcname2resource_dict

# EventRecord = Tuple[int, int, OperationType, str]  # (thread_id, timestamp, operation_type, address, function_name)
EventRecord = namedtuple("EventRecord", ["thread_id", "timestamp", "op_type", "addr", "resource_name", "function_name", "at_exit"])

class GlobalEventView:
	# Track all events across different threads over time
	def __init__(self):
		self.event_records: List[EventRecord] = []
		self.thread_id_set: Dict[str, int] = {}
		self.elapsed_time: int = 0.0  # ns

	def add_event_record(self, thread_id: str, timestamp: int, operation_type: OperationType, address: str, resource_name: str, function_name: str, at_exit: bool = False):
		# remapping thread_id to a dense range starting from 0
		if thread_id not in self.thread_id_set:
			self.thread_id_set[thread_id] = len(self.thread_id_set)
		thread_id = self.thread_id_set[thread_id]
     
		self.event_records.append(EventRecord(thread_id, timestamp, operation_type, address, resource_name, function_name, at_exit))

	def apply_fn(self, fn: Callable[[EventRecord], EventRecord]):
		self.event_records = [fn(record) for record in self.event_records]
		
	def sort_events(self):
		self.event_records.sort(key=lambda record: (record.timestamp, record.op_type.value))
		# Update elapsed time after sorting
		lowest_timestamp = self.event_records[0].timestamp
		self.elapsed_time = self.event_records[-1].timestamp - lowest_timestamp
		normalize_timestamp = lambda record: EventRecord(record[0], record[1] - lowest_timestamp, record[2], record[3], record[4], record[5], record[6])
		self.apply_fn(normalize_timestamp)
		
	def clean_empty_events(self):
		self.event_records = [record for record in self.event_records if record is not None and record.op_type != OperationType.UNDEFINED]

	def load_dir(self, pos2res_mapping: Dict[str, str], pos2func_mapping: Dict[str, str], dir_path: Union[str, os.PathLike],
                 thread_id_filter: Set[str] = None,
              	 timestamp_filter: Tuple[int, int] = None):
		# Load event records from a directory containing JSON files
		fp_list = []
		for filename in os.listdir(dir_path):
    		# thread_pid_tid.json
			if filename.endswith(".json"):
				pid = int(filename.split("_")[1])
				tid = filename.split("_")[2].split(".")[0]
				fp_list.append((pid, tid, os.path.join(dir_path, filename)))

		lowest_timestamp, highest_timestamp = timestamp_filter if timestamp_filter else (0, 1e20)
		for pid, tid, fp in fp_list:
			with open(fp, "r") as f:
				data = json.load(f)
			for res_id, record_list in data.items():
				for record in record_list:
					timestamp: int = int(record["ts_ns"])
					op_type_list: List[OperationType] = str2oper(record["event"])
					func_name = pos2func_mapping.get(str(record["function_index"]), "unknown_function")
					at_exit = record.get("is_exit", False)
					addr: str = record["ptr"]

					# unfold
					for op_type in op_type_list:
						self.add_event_record(tid, timestamp, op_type, addr, pos2res_mapping[res_id], func_name, at_exit)

					# lowest_timestamp = min(lowest_timestamp, timestamp)
					# highest_timestamp = max(highest_timestamp, timestamp)

		skip_some = lambda record: record if lowest_timestamp <= record.timestamp <= highest_timestamp else None

		# Post-processing: normalize timestamp and skip events in the first and last second to avoid potential noise from startup/shutdown
		self.apply_fn(skip_some)
		self.clean_empty_events()

		# Apply thread_id remapping and sort events by timestamp
		keep_thread = lambda record: record if thread_id_filter is None or record.thread_id in thread_id_filter else None
		self.apply_fn(keep_thread)
		self.clean_empty_events()

		self.sort_events()

	@property
	def num_events(self) -> int:
		return len(self.event_records)

	@property
	def num_threads(self) -> int:
		return len(self.thread_id_set)

	def __repr__(self):
		return f"GlobalEventView(event_records={len(self.event_records)}, threads={len(self.thread_id_set)}, elapsed_time={self.elapsed_time/1_000_000_000:.2f} s)"

	def __getitem__(self, index: int) -> EventRecord:
		return self.event_records[index]