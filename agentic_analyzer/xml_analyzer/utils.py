import os
import xmltodict
import chardet
import pickle
import enum
from typing import Union
from collections import namedtuple
from threading import Lock

class AnomonyType(enum.Enum):
	NO_METADATA = 0
	UNEXPECTED_FORMAT = 1
	UNEXPECTED_TYPE = 2
	KEY_MISSING = 3
	UNEXPECTED_NONE_VALUE = 4
	NO_FILE = 5
	IGNORED = 6
	NO_DEFINITION = 7

class ComponentType(enum.Enum):
	CLASS = 0
	FUNCTION = 1
	VARIABLE = 2
	DESCRIPTION = 3
	UNKNOWN = 10


AnomonyItem = namedtuple("AnomonyItem", ["anonomy_type", "component_type", "name", "detail"])

class Monitor:
	filename: str = "anonomy_logs.pkl"
	def __init__(self, lock: Lock = None):
		self.stat = []
		self.lock = lock if lock is not None else Lock()

	def log(self, anomony_type: AnomonyType, component_type: ComponentType, name: str, detail: str=""):
		with self.lock:
			self.stat.append(AnomonyItem(anomony_type, component_type, name, detail))
   
	def remove_duplicate_logs(self):
		with self.lock:
			unique_logs = set()
			unique_stat = []
			for log in self.stat:
				if log not in unique_logs:
					unique_logs.add(log)
					unique_stat.append(log)
			self.stat = unique_stat

	def load_from_file(self, filepath: Union[str, os.PathLike]):
		if os.path.isdir(filepath):
			filepath = os.path.join(filepath, self.filename)
			
		with open(filepath, "rb") as f:
			self.stat = pickle.load(f)

	def print_stats(self):
        # count logs by anonomy_type
		log_count_by_type = {}
		log_book = {}
		for log in self.stat:
			log_count_by_type.setdefault(log.anonomy_type, {})
			log_count_by_type[log.anonomy_type].setdefault(log.component_type, 0)
			log_count_by_type[log.anonomy_type][log.component_type] += 1
			
			# add to log book
			log_book.setdefault(log.anonomy_type, {})
			log_book[log.anonomy_type].setdefault(log.component_type, [])
			log_book[log.anonomy_type][log.component_type].append(log)

		for anonomy_type, component_counts in log_count_by_type.items():
			print(f"Anomony Type: {anonomy_type.name}")
			for component_type, count in component_counts.items():
				print(f"  Component Type: {component_type.name}, Count: {count}")

xml_file_cache = {}

def get_encoding(file):
	f = open(file, "rb")
	encoding = chardet.detect(f.read())["encoding"]
	f.close()
	return encoding


def read_file_obj(file):
	encoding = get_encoding(file)
	return open(file, "r", encoding=encoding)


def load_xml(file):
	if not os.path.exists(file):
		return None
    
	output_dict = xml_file_cache.get(file, None)
	if output_dict is None:
		file_obj = read_file_obj(file)
		output_dict = xmltodict.parse(file_obj.read())
		file_obj.close()
		xml_file_cache.setdefault(file, output_dict)
	return output_dict
