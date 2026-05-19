import os
import sys
import json
import pickle
import copy
import time
import asyncio
import numpy as np
import matplotlib.pyplot as plt

from tqdm import tqdm
from typing import Dict, Union, Tuple, List, Any, Iterable

# Set PYTHONPATH to the project root
os.environ["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
os.chdir(os.environ["PYTHONPATH"])
sys.path.insert(0, os.environ["PYTHONPATH"])

# Mark
os.environ["AGENTIC_ANALYZER_ENTRYPOINT"] = "type_analyzer"

from agentic_analyzer.cpp_parser import extract_base_type
from agentic_analyzer.helper import settings, PromptTemplateInitializer

from agentic_analyzer.xml_analyzer.utils import load_xml
from agentic_analyzer.xml_analyzer.functioninfo import FunctionInfo
from agentic_analyzer.xml_analyzer.classinfo import ClassInfo

from agentic_analyzer.formatter.v1.basic import BasicFormatter
from agentic_analyzer.gptquerier.v1.session import BasicSession


def load_all_function_info() -> List:
	index_file_dict = load_xml(os.path.join(settings.global_config.PATH_TO_XML, "index.xml"))

	system_files = []
	for compound in index_file_dict["doxygenindex"]["compound"]:
		if compound["@kind"] == "file":
			system_files.append(compound)

	function_infos = []
	for system_file in system_files:
		module_filepath = os.path.join(settings.global_config.PATH_TO_DOC_RESULTS, f"{system_file["@refid"]}.pkl")

		if not os.path.exists(module_filepath):
			raise FileNotFoundError(f"Module info file not found: {module_filepath}")

		with open(module_filepath, "rb") as f:
			module_info = pickle.load(f)

		function_infos.extend(module_info.get_all_functions())

	print(f"Total function infos loaded: {len(function_infos)}")
	return function_infos


def load_all_class_info() -> Dict:
	index_file_dict = load_xml(os.path.join(settings.global_config.PATH_TO_XML, "index.xml"))

	system_files = []
	for compound in index_file_dict["doxygenindex"]["compound"]:
		if compound["@kind"] == "file":
			system_files.append(compound)

	class_infos = {}
	typedef_num = 0
	num_failures = 0
	num_associated = 0
	for system_file in system_files:
		module_filepath = os.path.join(settings.global_config.PATH_TO_DOC_RESULTS, f"{system_file['@refid']}.pkl")

		if not os.path.exists(module_filepath):
			raise FileNotFoundError(f"Module info file not found: {module_filepath}")

		with open(module_filepath, "rb") as f:
			module_info = pickle.load(f)
			elem_info_list = module_info.get_classes()
			elem_info_with_name = {elem_info.get_name(): elem_info for elem_info in elem_info_list}
			refid_to_name = {elem_info.refid: elem_info.get_name() for elem_info in elem_info_list}

			typedef_num += len(module_info.typedefs)
			for old_ref, old_name, new_name in module_info.typedefs:
				# If we have refid
				if old_ref is not None and old_ref in refid_to_name:
					old_name = refid_to_name[old_ref]

				if old_name in elem_info_with_name:
					# Check local
					ref_class_info = copy.deepcopy(elem_info_with_name[old_name])
					ref_class_info.name = new_name
					elem_info_with_name[new_name] = ref_class_info
					num_associated += 1
				elif old_name in class_infos:
					# Check global bookkeeping
					ref_class_info = copy.deepcopy(class_infos[old_name])
					ref_class_info.name = new_name
					elem_info_with_name[new_name] = ref_class_info
					num_associated += 1
				else:
					num_failures += 1
    
		class_infos.update(elem_info_with_name)

	print(f"Total types found: {len(class_infos) - num_associated}")
	print(f"Total typedefs seen: {typedef_num}")
	print(f"Total successfully associated typedefs: {num_associated}")
	print(f"Total failed typedefs association: {num_failures}")
	print(f"Total type infos after association: {len(class_infos)}")
	return class_infos


class FewShotExampleLoader:
	def __init__(self, example_file_path: Union[str, os.PathLike]):

		with open(example_file_path, 'r', encoding='utf-8') as f:
			self.examples = json.load(f)

		self.example_str = None

	def get_example_str(self) -> str:
		if self.example_str is not None:
			return self.example_str

		example_template = """Example {index}:\n{source}\nOutput:\n{expected}\nReason:{reason}\n\n"""

		self.example_str = "===START OF EXAMPLE===\n"
		for idx, example in self.examples.items():
			self.example_str += example_template.format(index=idx, source=example["source"],
														expected=example["expected"], reason=example["reason"])

		self.example_str += "===END OF EXAMPLE===\n"

		return self.example_str


class TypeSrcFormatter(BasicFormatter):
	def __init__(self, prompt_template_path: Union[str, os.PathLike], example_str: str = ""):
		# Use v2 prompt template, which includes few-shot examples, for source code analysis stage
		if prompt_template_path is not None:
			with open(prompt_template_path, 'r', encoding='utf-8') as f:
				prompts = json.load(f)
		self.prompt = prompts["introduction"] + example_str + prompts["instruction"]

	def prompt_fill(self, type_info: ClassInfo) -> str:
		src_lines = type_info.read_source_code(settings.global_config.PATH_TO_TARGET_PROJECT)
		src_string = "\n".join(src_lines)
		message = f"===START OF SOURCE===\n{src_string}\n===END OF SOURCE===\nwhere the type is:{type_info.name}"
		return message


class ApiFormatter(BasicFormatter):
	def prompt_fill(self, infos: Tuple[FunctionInfo, str]) -> str:
		fn, involved_type_names = infos
		api_string = f"{fn.get_name()}: {fn.ordered_param_str}, (idx=ret: {fn.get_rettype().replace('static ','').strip()})"
		message = f"===START OF DECLARATION===\n{api_string}\n===END OF DECLARATION===\nwhere involved resource types are: {involved_type_names}.\n"
		# message += "Please answer whether the function involves resource management operations (YES or NO) for each involved resource type."
		return message

class SrcFormatter(BasicFormatter):
	def __init__(self, prompt_template_path: Union[str, os.PathLike], example_str: str = ""):
		# Use v2 prompt template, which includes few-shot examples, for source code analysis stage
		if prompt_template_path is not None:
			with open(prompt_template_path, 'r', encoding='utf-8') as f:
				prompts = json.load(f)
		self.prompt = prompts["introduction"] + example_str + prompts["instruction"]

	def prompt_fill(self, infos: Tuple[FunctionInfo, str]) -> str:
		fn, involved_type_names = infos
		src_lines = fn.read_source_code(settings.global_config.PATH_TO_TARGET_PROJECT)
		src_string = "\n".join(src_lines)
		message = f"===START OF SOURCE===\n{src_string}\n===END OF SOURCE===\nwhere involved resource types are: {involved_type_names}."
		return message


async def analyze_type_def_check(types_to_check: Iterable[ClassInfo],
						   		 output_dir: Union[str, os.PathLike]) -> Dict[str, List[ClassInfo]]:
	uncached = []
	stage_id = "TYPE_DEF_CHECK"
	persistent_result_path = os.path.join(output_dir, f"{stage_id}.pkl")

	if os.path.exists(persistent_result_path):
		with open(persistent_result_path, "rb") as f:
			persistent_result = pickle.load(f)
	else:
		persistent_result = {
			"PASS": [],
			"FAIL": []
		}

	# Skip already analyzed types
	cached = set()
	for type_info in persistent_result["PASS"] + persistent_result["FAIL"]:
		cached.add(type_info.refid)
	for type_info in types_to_check:
		if type_info.refid in cached:
			continue
		uncached.append(type_info)

	example_loader = FewShotExampleLoader(example_file_path=os.path.join(settings.global_config.TEMPORARY_PROMPT_PATH, "TYPE_CASES",
                                                                         f"{settings.global_config.SYSTEM_NAME.lower()}.json"))
	example_str = example_loader.get_example_str()
	type_src_formatter = TypeSrcFormatter(os.path.join(settings.global_config.TEMPORARY_PROMPT_PATH, "TYPE_CHECK_PROMPT.json"), example_str)
	src_session = BasicSession(api_key=settings.global_config.PROVIDER_CONFIG.api_key,
							   model=settings.global_config.PROVIDER_CONFIG.model,
							   provider=settings.global_config.PROVIDER_CONFIG.provider,
							   valid_reply_set=["YES", "NO"], allow_multiple_indicators=False)

	failures = []
	print(f"Total functions to check with TYPE CHECK stage: {len(uncached)}, now creating tasks...")
	tasks = [src_session.step(type_src_formatter.prompt_gen(type_info), type_info.name, type_info) for type_info in uncached]
	results = []

	for corontine in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
		result = await corontine
		results.append(result)

	for parsed, type_info in tqdm(results, desc="Post-processing results"):
		if parsed is None:
			failures.append(type_info.name)
			print(f"Type {type_info.name} got invalid reply, {parsed}, skip.")
			continue

		# Get the results:
		# type_info.name:YES/NO, e.g., Item_func_curtime:NO
		answer = parsed.pop(type_info.name)  # ensure the key is the type name instead of the refid

		# Store the result
		if answer == "YES":
			force_failures = {"Item", "Field"}
			if type_info.name in force_failures:
				print(f"Type {type_info.name} is forced to FAIL due to its name containing keywords {force_failures}.")
				persistent_result["FAIL"].append(type_info)
			else:
				persistent_result["PASS"].append(type_info)
		else:
			persistent_result["FAIL"].append(type_info)

	# Persist after each function to avoid data loss
	with open(persistent_result_path, "wb") as f:
		pickle.dump(persistent_result, f)

	if len(uncached) > 0:
		print(f"Func analysis stage completed. Stats:")
		for usage_key, usage_value in src_session.usage_stats.items():
			print(f"{usage_key}: {usage_value}")
	return persistent_result


async def analyze_function_api_check(union_function: List[Tuple[FunctionInfo, str]],
					 		  	 	 output_dir: Union[str, os.PathLike],
           					   		 excludes: List[str] = []) -> Dict[str, List[Tuple[FunctionInfo, str]]]:
	# If it is unlikely important, we need to go through the api check first
	uncached = []
	stage_id = "CHECK_FUNC_API"
	persistent_result_path = os.path.join(output_dir, f"{stage_id}.pkl")

	if os.path.exists(persistent_result_path):
		with open(persistent_result_path, "rb") as f:
			persistent_result = pickle.load(f)
	else:
		persistent_result = {
			"KEEP": [],
			"IGNORE": []
		}

	# Skip already analyzed functions
	cached = set()
	for fn, _ in persistent_result["KEEP"] + persistent_result["IGNORE"]:
		cached.add(fn.refid)
	for fn, type_names in union_function:
		if fn.refid in cached:
			continue

		to_be_excluded = False
		for ex in excludes:
			if fn.get_name() == ex:
				to_be_excluded = True
				break

		if to_be_excluded:
			continue

		uncached.append((fn, type_names))


	api_formatter = ApiFormatter(os.path.join(settings.global_config.TEMPORARY_PROMPT_PATH, "API_CHECK_PROMPT.json"))
	api_session = BasicSession(api_key=settings.global_config.PROVIDER_CONFIG.api_key,
							   model=settings.global_config.PROVIDER_CONFIG.model,
							   provider=settings.global_config.PROVIDER_CONFIG.provider,
							   valid_reply_set=["YES", "NO"], allow_multiple_indicators=False)
	failures = []
	print(f"Total functions to check with API stage: {len(uncached)}, now creating tasks...")
	tasks = [api_session.step(api_formatter.prompt_gen((fn, type_names)), type_names, (fn, type_names)) for fn, type_names in uncached]
	results = []

	for corontine in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
		result = await corontine
		results.append(result)
 
	for parsed, tuple_fn_types in tqdm(results, desc="Post-processing API check results"):
		fn, type_names = tuple_fn_types
		if parsed is None:
			failures.append(fn.get_name())
			print(f"Function {fn.get_name()} got invalid reply, skip.")
			continue

		if any([answer == "YES" for _, answer in parsed.items()]):
			persistent_result["KEEP"].append((fn, type_names))
		else:
			persistent_result["IGNORE"].append((fn, type_names))

	# Persist after each function to avoid data loss
	with open(persistent_result_path, "wb") as f:
		pickle.dump(persistent_result, f)

	if len(uncached) > 0:
		print(f"API check stage completed. Stats:")
		for usage_key, usage_value in api_session.usage_stats.items():
			print(f"{usage_key}: {usage_value}")
	return persistent_result

async def analyze_function_by_def(union_function: List[Tuple[FunctionInfo, str]],
						 		  output_dir: Union[str, os.PathLike],
								  excludes: List[str] = []) -> Tuple[List[Tuple[FunctionInfo, Dict[str, str]]], List[str]]:
	# Now process the likely important functions and the kept unlikely important functions
	stage_id = "FINAL_TYPE_ANALYSIS"
	persistent_result_path = os.path.join(output_dir, f"{stage_id}.pkl")
	if os.path.exists(persistent_result_path):
		with open(persistent_result_path, "rb") as f:
			persistent_result = pickle.load(f)
	else:
		# python object for persistent storage
		# List[Tuple[FunctionInfo, Dict[str, str]]
		# Dict[str, str]: resource type -> List of operation types separated by comma
		persistent_result = []
	
	# Skip already analyzed functions
	cached = set()
	uncached = []
	for fn, _ in persistent_result:
		cached.add(fn.refid)
	for fn, type_names in union_function:
		if fn.refid in cached:
			continue

		to_be_excluded = False
		for ex in excludes:
			if fn.get_name() == ex:
				to_be_excluded = True
				break

		if to_be_excluded:
			debug_src_formatter = SrcFormatter(os.path.join(settings.global_config.TEMPORARY_PROMPT_PATH, "DEF_CHECK_PROMPT.json"))
			debug_prompt = debug_src_formatter.prompt_gen((fn, type_names))
			print(f"Function {fn.get_name()} is excluded from analysis. Generated prompt:")
			print(debug_prompt)
			print("===" * 10)
			continue

		uncached.append((fn, type_names))

	example_loader = FewShotExampleLoader(example_file_path=os.path.join(settings.global_config.TEMPORARY_PROMPT_PATH, "FUNC_CASES",
                                                                         f"{settings.global_config.SYSTEM_NAME.lower()}.json"))
	example_str = example_loader.get_example_str()
	src_formatter = SrcFormatter(os.path.join(settings.global_config.TEMPORARY_PROMPT_PATH, "DEF_CHECK_PROMPT.json"), example_str)
	src_session = BasicSession(api_key=settings.global_config.PROVIDER_CONFIG.api_key,
							   model=settings.global_config.PROVIDER_CONFIG.model,
							   provider=settings.global_config.PROVIDER_CONFIG.provider,
							   valid_reply_set=["ACQUIRE", "USE", "WAIT", "RELEASE", "ACCESS", "GET"], allow_multiple_indicators=True)
	
	failures = []
	print(f"Total functions to check with DEF stage: {len(uncached)}, now creating tasks...")
	tasks = [src_session.step(src_formatter.prompt_gen((fn, type_names)), type_names, (fn, type_names)) for fn, type_names in uncached]
	results = []

	for corontine in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
		result = await corontine
		results.append(result)

	for parsed, tuple_fn_types in tqdm(results, desc="Post-processing DEF check results"):
		fn, type_names = tuple_fn_types

		if parsed is None:
			failures.append(fn.get_name())
			print(f"Function {fn.get_name()} got invalid reply, skip.")
			continue

		# Store the result
		persistent_result.append((fn, parsed))

	# Persist after each function to avoid data loss
	with open(persistent_result_path, "wb") as f:
		pickle.dump(persistent_result, f)

	if len(uncached) > 0:
		print(f"Func analysis stage completed. Stats:")
		for usage_key, usage_value in src_session.usage_stats.items():
			print(f"{usage_key}: {usage_value}")

	return persistent_result, failures


def unify_type_name(type_name: str) -> str:
	if not isinstance(type_name, str) or not type_name.strip():
		return None  # or return "" based on downstream usage

	modifiers = {"inline", "static", "const", "extern", "volatile",
			  	 "const*", "const&", "*const", "&const"}

	real_name = type_name.split("::")[-1]

	words = real_name.split()
	unified_type_name_words = [w for w in words if w not in modifiers]

	unified_type_name = " ".join(unified_type_name_words).strip(" *&")

	return unified_type_name

debug_type_set = set()

def is_valid_type_name(type_name: str) -> bool:
	if type_name is None or type_name.strip() == "":
		return False

	invalid_char = {"(", ")", "[", "]", "&", "||", "?", ":", ";", ".", "+", "-", "/", "\\", "^", "%", "$", "#", "@", "!", "~", "`"}

	if any(char in type_name for char in invalid_char):
		return False

	# common buldtin types
	builtin_types = {"int", "char", "float", "double", "void", "bool", "size_t", "ssize_t", "ptrdiff_t", "wchar_t", "char16_t", "char32_t",
                   	"uint8_t", "uint8", "uint16_t", "uint32_t", "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t"}

	if type_name in builtin_types or any(builtin_type in type_name for builtin_type in builtin_types):
		return False

	return True

def build_param_to_function_info_dict(function_infos: List[FunctionInfo], include_this_pointer: bool = True) -> Dict[str, List[FunctionInfo]]:
	"""Build a mapping from parameter/return type names to FunctionInfo objects."""
	param_to_function_info_dict = {}
	for function_info in tqdm(function_infos):
		# Params
		for param_info in function_info.get_params():
			unified_type_name = extract_base_type(param_info.get_type())
			if not is_valid_type_name(unified_type_name):
				continue
			debug_type_set.add(unified_type_name)
			param_to_function_info_dict.setdefault(unified_type_name, []).append(function_info)

		# "This" pointer for member functions
		if include_this_pointer and "::" in function_info.name:
			# TODO: consider corner cases like definitions within classes
			class_name = function_info.name.split("::")[0]
			function_info.class_member_of = class_name
			param_to_function_info_dict.setdefault(class_name, []).append(function_info)

		# Return Type
		if "void*" in function_info.get_rettype() or "void *" in function_info.get_rettype():
			debug_type_set.add("void*")
			param_to_function_info_dict.setdefault("void*", []).append(function_info)
			continue
  
		unified_return_type_name = extract_base_type(function_info.get_rettype())
		if not is_valid_type_name(unified_return_type_name):
			continue
		debug_type_set.add(unified_return_type_name)
		param_to_function_info_dict.setdefault(unified_return_type_name, []).append(function_info)

	# Remove redundant function infos in the lists
	for key in param_to_function_info_dict:
		seen = set()
		unique_funcs = []
		for func in param_to_function_info_dict[key]:
			if func.get_name() in seen:
				continue

			# Make sure each function only appears once
			seen.add(func.get_name())
			unique_funcs.append(func)

		param_to_function_info_dict[key] = unique_funcs

	return param_to_function_info_dict


def get_union_functions(param_to_function_infos_dict: Dict[str, List[FunctionInfo]], type_list: List[str]) -> List[Tuple[FunctionInfo, str]]:
	func2type_cache = {}
	for t in type_list:
		func_infos = param_to_function_infos_dict.get(t, [])
		for finfo in func_infos:
			func2type_cache.setdefault(finfo, []).append(t)

	union_func_list = []
	valid_relations = 0
	for finfo, type_names in func2type_cache.items():
		union_func_list.append((finfo, ",".join(type_names)))
		valid_relations += len(type_names)
	print(f"Total valid relations between types and functions: {valid_relations}")
	return union_func_list


def dump_analysis_result(analysis_result: List[Tuple[FunctionInfo, Dict[str, str]]], output_dir: Union[str, os.PathLike]):
	# Dump to JSON for easier inspection
	json_compatible_result = {}
	for fn, type_op_dict in analysis_result:
		json_compatible_result[fn.get_name()] = type_op_dict

	with open(os.path.join(output_dir, "analysis_result.json"), "w") as f:
		json.dump(json_compatible_result, f, indent=4)


if __name__ == "__main__":
	if not os.path.exists(settings.global_config.PATH_TO_DOC_RESULTS):
		raise FileNotFoundError(f"Doc tokenizer results path not found: {settings.global_config.PATH_TO_DOC_RESULTS}")
	if not os.path.exists(settings.global_config.PATH_TO_OUTPUT):
		os.makedirs(settings.global_config.PATH_TO_OUTPUT)

	# Initialize prompt templates (format)
	PromptTemplateInitializer.instantiate_template(settings.global_config.SYSTEM_NAME,
												   settings.global_config.PROMPT_TEMPLATE_PATH,
												   settings.global_config.TEMPORARY_PROMPT_PATH)
	
	# Prepare: Get all function infos and build dict and get all files
	all_function_infos = load_all_function_info()
	all_class_infos = load_all_class_info()

	# Buggy here:
	# Need to find a way to select a wider range of functions that relates to params
	param_to_function_infos_dict = build_param_to_function_info_dict(all_function_infos, include_this_pointer=True)
	all_types_appeared = set(param_to_function_infos_dict.keys())
	num_all_types_appeared = len(all_types_appeared)

	valid_types = set()
	unique_types = {}

	# Intersect, we only analyze the types that have appeared in the function signatures and have definition in the docs
	for resource in all_types_appeared:
		if resource not in all_class_infos:
			param_to_function_infos_dict.pop(resource)
			continue

		info = all_class_infos[resource]
		valid_types.add(resource)
		unique_types[info.refid] = info  # avoid duplicate requests to LLM for the same type through different aliases

	print(f"Total types appeared: {num_all_types_appeared}, in-doc: {len(valid_types)}, "
       	  f"no-record: {num_all_types_appeared - len(valid_types)}, unique: {len(unique_types)}")
	assert len(valid_types) == len(param_to_function_infos_dict), "Mismatch between valid types and param_to_function_infos_dict keys after filtering."

	# request LLM to check all types
	type_check_results = asyncio.run(analyze_type_def_check(unique_types.values(), output_dir=settings.global_config.PATH_TO_OUTPUT))
	type_of_interest = set([type_info.name for type_info in type_check_results["PASS"]])
	print(f"Total types of interest: {len(type_of_interest)}")

	union_functions = get_union_functions(param_to_function_infos_dict, type_of_interest)
	print(f"Total functions related to the resource types: {len(union_functions)}")

	# likely to be resource related types
	keyword_lists = [
		"acquire", "get", "open", "create", "init", "allocate", "alloc", "new", "build", "fetch",
		"free", "release", "close", "delete", "destroy", "dealloc", "remove", "drop", "clear", "reset",
		"update", "set", "put", "write", "store", "insert", "add", "append", "load", "read", "find", "search",
		"lookup", "access", "check", "validate", "verify", "lock", "unlock", "wait", "signal", "notify", "send", "receive", "recv",
		"start", "stop", "run", "execute", "process", "handle", "dispatch", "schedule", "trigger", "raise", "flush", "block", "commit"
	]

	def filter_with_keywords(func_info: FunctionInfo, keywords: List[str]) -> bool:
		func_name_lower = func_info.get_name().lower()
		if "::" in func_name_lower:
			func_name_lower = func_name_lower.split("::")[-1]
		indicators = [keyword in func_name_lower for keyword in keywords]
		return any(indicators)

	dist = []
	dist_bk = []
	for resource in type_of_interest:
		assert resource in param_to_function_infos_dict, f"Resource {resource} not found in function infos."
		dist.append(len(param_to_function_infos_dict[resource]))
		dist_bk.append((len(param_to_function_infos_dict[resource]), resource))
	# Calculate 3 sigma
	dist_std = np.std(dist)
	dist_mean = np.mean(dist)
	threshold = dist_mean + 3 * dist_std
	for count, resource in dist_bk:
		if count > threshold:
			print(f"Resource {resource} has {count} related functions, which is above the 3-sigma threshold of {threshold:.2f}. Consider reviewing these functions separately.")

	likely_important_functions: List[Tuple[FunctionInfo, str]] = []
	unlikely_important_functions: List[Tuple[FunctionInfo, str]] = []
	for fn, type_names in union_functions:
		if not filter_with_keywords(fn, keyword_lists):
			unlikely_important_functions.append((fn, type_names))
			continue
		likely_important_functions.append((fn, type_names))

	# Only analyze functions once and associates them to multiple classes if needed
	print(f"Likely important functions: {len(likely_important_functions)}")
	check_result = asyncio.run(analyze_function_api_check(unlikely_important_functions, output_dir=settings.global_config.PATH_TO_OUTPUT))
	combined_functions = likely_important_functions + check_result["KEEP"]
	print(f"Total functions to be analyzed in detail: {len(combined_functions)}")
	analysis_result, failures = asyncio.run(analyze_function_by_def(combined_functions, output_dir=settings.global_config.PATH_TO_OUTPUT))

	print(f"Total analyzed functions: {len(analysis_result)}")
	dump_analysis_result(analysis_result, output_dir=settings.global_config.PATH_TO_OUTPUT)
