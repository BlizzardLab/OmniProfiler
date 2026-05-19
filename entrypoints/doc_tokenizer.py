import os
import sys
import pickle
import tqdm
import time

from typing import Dict, Set, Union, List
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

# Set PYTHONPATH to the project root
os.environ["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
os.chdir(os.environ["PYTHONPATH"])
sys.path.insert(0, os.environ["PYTHONPATH"])

# Mark
os.environ["AGENTIC_ANALYZER_ENTRYPOINT"] = "doc_tokenizer"

from agentic_analyzer.helper import settings
from agentic_analyzer.xml_analyzer.utils import load_xml, Monitor
from agentic_analyzer.xml_analyzer.module_info import ModuleInfo

def tokenize_xml_file(file_info: Dict,
					  enumvalue_refids: Set,
					  monitor: Monitor,
					  path_to_project: Union[str, os.PathLike],
					  path_to_xml: Union[str, os.PathLike],
					  path_to_save: Union[str, os.PathLike],
					  verbose: bool = False, dry_run: bool = False):
	assert file_info["@kind"] == "file"
	
	refid = file_info["@refid"]
	
	# Check if already processed
	result_file = os.path.join(path_to_save, f"{refid}.pkl")
	if os.path.exists(result_file):
		# Skip already processed files
		if verbose:
			print(f"Skipping already processed file: {refid}")
		return
	
	if verbose:
		print(f"Processing file: {refid}")
	
	if dry_run:
		time.sleep(0.01)  # Simulate some processing time
		return
	
	# Process the XML file
	module_info = ModuleInfo()
	module_info.load(refid, path_to_xml, enumvalue_refids, monitor)
	
	# # Save the tokenized result
	with open(result_file, "wb") as f:
		pickle.dump(module_info, f)


if __name__ == "__main__":
	# Load XML Index
	index_file = os.path.join(settings.global_config.PATH_TO_XML, "index.xml")
	index_dict = load_xml(index_file)
	
	# Get all XML files from index
	all_xml_files = index_dict["doxygenindex"]["compound"]
	
	# Filter only XML files of kind 'file'
	all_xml_files = [f for f in all_xml_files if f["@kind"] == "file"]

	# Find all enumvalue refids to exclude
	enumvalue_refids = set()
	exclude_kinds = ["enumvalue", "enum"]
	for compound in index_dict["doxygenindex"]["compound"]:
		if "member" in compound:
			if isinstance(compound["member"], List):
				for member in compound["member"]:
					if member["@kind"] in exclude_kinds:
						enumvalue_refids.add(member["@refid"])
			elif isinstance(compound["member"], Dict):
				member = compound["member"]
				if member["@kind"] in exclude_kinds:
					enumvalue_refids.add(member["@refid"])
	
	# Remove duplicates based on refid
	unique_refids = set()
	all_xml_files = [f for f in all_xml_files if not (f["@refid"] in unique_refids or unique_refids.add(f["@refid"]))]
	
	print(f"Found {len(all_xml_files)} XML files to process.")
	
	# Prepare progress bar and lock
	progress_lock = Lock()
	progress_bar = tqdm.tqdm(total=len(all_xml_files))
	def update_progress_callback(future):
		with progress_lock:
			progress_bar.update(1)
	
	# Monitor for logging
	monitor = Monitor()
	
	# Wrapper to submit tasks
	def task_submit_wrapper(executor: ThreadPoolExecutor, file_info: Dict):
		future = executor.submit(tokenize_xml_file,
								 file_info,
								 enumvalue_refids,  # for exclusion
								 monitor,
								 settings.global_config.PROJECT_HOME,           # path_to_project
								 settings.global_config.PATH_TO_XML,            # path_to_xml
								 settings.global_config.PATH_TO_DOC_RESULTS,    # path_to_save
								 verbose=False, dry_run=False)
		future.add_done_callback(update_progress_callback)
		return future
	
	# # Process XML files in parallel
	with ThreadPoolExecutor(max_workers=24) as executor:
		futures = [ task_submit_wrapper(executor, file_info) for file_info in all_xml_files ]
		
		for future in futures:
			future.result()

	# Remove duplicate logs
	monitor.remove_duplicate_logs()
		
	print(f"\nAnomony Logs: {len(monitor.stat)} entries found.")
	
	with open(os.path.join(settings.global_config.PATH_TO_DOC_RESULTS, "anonomy_logs.pkl"), "wb") as f:
		pickle.dump(monitor.stat, f)

	with open(os.path.join(settings.global_config.PATH_TO_DOC_RESULTS, "enumvalue_refids.txt"), "w", encoding="utf-8") as f:
		for refid in enumvalue_refids:
			f.write(f"{refid}\n")

	monitor.print_stats()
