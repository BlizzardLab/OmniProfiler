import os
import copy
import json
import argparse

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Collect and aggregate results from multiple JSON files.")
	parser.add_argument("--sanity-check", action="store_true", help="Perform a sanity check on the aggregated results.", default=True)
	parser.add_argument("--input-dir", help="Directory containing input JSON files to aggregate.")
	parser.add_argument("--output-dir", help="Output directory to write the aggregated results.")
	parser.add_argument("--merge-type", action="store_true", help="Merge GET/ACQUIRE, ACCESS/USE", default=False)
	args = parser.parse_args()

	input_files = [os.path.join(args.input_dir, f) for f in os.listdir(args.input_dir) if f.endswith(".json")]
	aggregated_results = {}
	global_resource_mapping = {}	# Mapping of resource name between a unique index for later instrumentation
	global_function_mapping = {}	# Mapping of function name between a unique index for later instrumentation

	for input_file in input_files:
		with open(input_file, "r") as f:
			data = json.load(f)  # dict with structure {key: {"__metadata__": {...}, subkey: [{sb: sv},{sb: sv}] }}
			if data is None:
				print(f"Warning: No data found in file '{input_file}'. Skipping.")
				continue
			for fn_name, fn_data in data.items():
				duplicate_check = False
				if fn_name in aggregated_results:
					duplicate_check = True
				can_be_aggregated = False
				# Copy subkeys and values
				new_fn_data_dict = {}

				for resource_name, position_list in fn_data.items():        
					if resource_name == "__metadata__":
						continue  # Skip metadata since they share the same range

					if position_list is None:
						# ignore
						continue

					new_position_list = []
					for position_dict in position_list:  # [{"flags": "ACQUIRE,USE,RELEASE,..."}]
						flag_str = position_dict["flags"]
      
						if "DONE" not in flag_str:
							if args.sanity_check:
								raise ValueError(f"Expected 'DONE' in values for key '{fn_name}' and subkey 'flags' in file '{input_file}'. Found: '{flag_str}'")
							else:
								print(f"Warning: 'DONE' not found for key '{fn_name}' and subkey 'flags' in file '{input_file}'. Values: '{flag_str}'")
			
						if "INVALID" in flag_str:
							if args.sanity_check:
								raise ValueError(f"Sanity check failed for key '{fn_name}' and subkey 'flags' in file '{input_file}'. Found 'INVALID' in values: '{flag_str}'")
							else:
								print(f"Warning: 'INVALID' found for key '{fn_name}' and subkey 'flags' in file '{input_file}'. Values: '{flag_str}'")

						# Remove "[,]DONE", "INVALID" and space in values if present
						# Also handle type merges
						flag_list = [v.strip() for v in flag_str.split(",") if v.strip() != "DONE" and v.strip() != "INVALID"]
						if args.merge_type:
							merged_flags = set()
							for flag in flag_list:
								if flag in ["GET", "ACQUIRE"]:
									merged_flags.add("ACQUIRE")
								elif flag in ["ACCESS", "USE"]:
									merged_flags.add("USE")
								else:
									merged_flags.add(flag)
							flag_list = list(merged_flags)
							flag_str = ",".join(flag_list)
						else:
							flag_str = ",".join(flag_list)

						if flag_str == "":
							continue  # Skip if values become empty after cleaning

						# Now, surely this item is effective for aggregation, we can add it to metadata
						demangled_fn_name = fn_data["__metadata__"]["demangled_name"]
						# If it is a new function name
						if fn_name not in global_function_mapping:
							global_function_mapping[fn_name] = len(global_function_mapping)
						# If it is off the record
						if "function_index" not in fn_data["__metadata__"]:
							fn_data["__metadata__"]["function_index"] = global_function_mapping[fn_name]

						# It it is a new resource type
						if resource_name not in global_resource_mapping:
							global_resource_mapping[resource_name] = len(global_resource_mapping)

						new_dict = copy.deepcopy(position_dict)
						new_dict["flags"] = flag_str  # Update with cleaned values
						new_dict["position"] = -1 if new_dict["position"] == 2147483648 else new_dict["position"]  # Handle special case for position value
						new_dict["resource_index"] = global_resource_mapping[resource_name]  # Add global resource index for later instrumentation
						new_position_list.append(new_dict)
						can_be_aggregated = True

					if len(new_position_list) != 0:
						new_fn_data_dict[resource_name] = new_position_list

				if not can_be_aggregated:
					print(f"Warning: No valid resource access found for function '{fn_name}' in file '{input_file}'. Skipping this function.")
					continue

				# Copy metadata
				assert "__metadata__" in fn_data, f"Expected '__metadata__' key in data for function '{fn_name}' in file '{input_file}'."
				if duplicate_check:
					if "__metadata__" in aggregated_results[fn_name]:
						if any([aggregated_results[fn_name]["__metadata__"][key] != fn_data["__metadata__"][key] for key in aggregated_results[fn_name]["__metadata__"].keys() if key != "function_index"]):  # Allow function_index to be different since it is assigned based on the order of processing
							if args.sanity_check:
								raise ValueError(f"Conflict detected in metadata for function '{fn_name}' in file '{input_file}'. Existing metadata: '{aggregated_results[fn_name]['__metadata__']}', New metadata: '{fn_data['__metadata__']}'")
							else:
								print(f"Warning: Conflict detected in metadata for function '{fn_name}' in file '{input_file}'. Existing metadata: '{aggregated_results[fn_name]['__metadata__']}', New metadata: '{fn_data['__metadata__']}'")

					if aggregated_results[fn_name] == new_fn_data_dict:
						print(f"Duplicate entry for function '{fn_name}' in file '{input_file}' matches existing entry. Skipping.")
						continue

				new_fn_data_dict["__metadata__"] = fn_data["__metadata__"]  # Start with metadata, which is expected to be the same for duplicates

				if can_be_aggregated:
					aggregated_results[fn_name] = new_fn_data_dict
        

	with open(os.path.join(args.output_dir, "aggregated_results.json"), "w") as f:
		json.dump(aggregated_results, f, indent=4)

	with open(os.path.join(args.output_dir, "global_resource_mapping.json"), "w") as f:
		json.dump(global_resource_mapping, f, indent=4)

	with open(os.path.join(args.output_dir, "global_function_mapping.json"), "w") as f:
		json.dump(global_function_mapping, f, indent=4)

	print(f"Aggregated results have been written to {os.path.join(args.output_dir, 'aggregated_results.json')}")
	print(f"Global resource mapping has been written to {os.path.join(args.output_dir, 'global_resource_mapping.json')}")
	print(f"Global function mapping has been written to {os.path.join(args.output_dir, 'global_function_mapping.json')}")
