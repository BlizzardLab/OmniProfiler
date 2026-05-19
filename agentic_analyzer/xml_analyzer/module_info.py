import os
import time
import numpy as np

from threading import Lock
from typing import Union, Set, List

import agentic_analyzer.xml_analyzer.utils as utils
from agentic_analyzer.xml_analyzer.classinfo import ClassInfo
from agentic_analyzer.xml_analyzer.functioninfo import FunctionInfo
from agentic_analyzer.xml_analyzer.variableinfo import VariableInfo
from agentic_analyzer.xml_analyzer.filenameinfo import FilenameInfo


class ModuleInfo:

	def __init__(self):
		self.refid = None
		self.filename = None
		self.classes = []
		self.functions = []
		self.variables = []
		self.typedefs = []

	def __try_find_memberdef(self, kind, refid: str, path_to_xml: Union[str, os.PathLike] = None):
		target_file = "_".join(refid.split("_")[:-1])
		target_file_dict = utils.load_xml(os.path.join(path_to_xml, "{}.xml".format(target_file)))
		memberdef_dict = None
		if "sectiondef" in target_file_dict["doxygen"]["compounddef"]:
			sectiondef_dict = target_file_dict["doxygen"]["compounddef"]["sectiondef"]
			for components_dict in np.array([sectiondef_dict]).flatten():
				if components_dict["@kind"] == kind:
					for component_dict in np.array([components_dict["memberdef"]]).flatten():
						if component_dict["@id"] == refid:
							memberdef_dict = component_dict
		return memberdef_dict

	def load(self, refid: str, path_to_xml: Union[str, os.PathLike], enumvalue_refids: Set, monitor: utils.Monitor, verbose: bool = False):
		self.refid = refid

		module_file = os.path.join(path_to_xml, f"{refid}.xml")

		if not os.path.exists(module_file):
			raise FileNotFoundError(f"Module XML file not found: {module_file}")

		module_dict = utils.load_xml(module_file)

		if "innerclass" in module_dict["doxygen"]["compounddef"].keys():
			for class_metadata in np.array([module_dict["doxygen"]["compounddef"]["innerclass"]]).flatten():
				# Manual load class info
				class_info = ClassInfo()
				class_info.load(class_metadata["@refid"], path_to_xml, enumvalue_refids, monitor, verbose=verbose)
				self.classes.append(class_info)

		rename_typedef_refid_to_name = {}
		if "sectiondef" in module_dict["doxygen"]["compounddef"].keys():
			for components_dict in np.array([module_dict["doxygen"]["compounddef"]["sectiondef"]]).flatten():
				components_memberdef_list = []
				if "memberdef" not in components_dict:
					for component_ref_dict in np.array([components_dict["member"]]).flatten():
						components_memberdef_list.append(
							self.__try_find_memberdef(components_dict["@kind"], component_ref_dict["@refid"], path_to_xml)
						)
				else:
					components_memberdef_list.extend(np.array([components_dict["memberdef"]]).flatten())

				if components_dict["@kind"] == "func":
					for component_dict in components_memberdef_list:
						if component_dict is None:
							continue
						try:
							function_info = FunctionInfo()
							function_info.extract(component_dict, monitor=monitor, verbose=verbose)
							self.functions.append(function_info)
						except AssertionError:
							pass
				elif components_dict["@kind"] == "var":
					for component_dict in components_memberdef_list:
						variable_info = VariableInfo()
						variable_info.extract(component_dict, monitor=monitor, verbose=verbose)
						self.variables.append(variable_info)
				elif components_dict["@kind"] == "typedef":
					# Handle typedef (for renaming or struct definitions)
					for component_dict in components_memberdef_list:
						if "memberdef" in components_dict:
							# typedef xxx {} yyy; case, we can directly get the new name
							# component_dict["type"]["ref"] may be a list (complex type definition such as tempalate)
							# where component_dict["type"]["ref"][0]["#text"] must be an old type name
							# TODO: new name is easy to get, but old name may be hard to get, therefore we just need to note down the refid for later use
							if isinstance(component_dict["type"], str):
								assert "@refid" not in component_dict, f"Unexpected @refid in type string, {component_dict}"
								old_ref = None
								old_name = component_dict["type"]
							elif isinstance(component_dict["type"]["ref"], List):
								# Note: maybe a composite type definition such as template, we just use the @refid for reference
								old_ref = component_dict["type"]["ref"][0]["@refid"]
								old_name = component_dict["type"]["ref"][0]["#text"]
							elif isinstance(component_dict["type"]["ref"], dict):
								old_ref = component_dict["type"]["ref"]["@refid"]
								old_name = component_dict["type"]["ref"]["#text"]
							new_name = component_dict["name"]
							# print(f"Found typedef: {new_name} -> {old_ref}, old name: {old_name}")
							self.typedefs.append((old_ref, old_name, new_name))
						elif "member" in components_dict:
    	  					# Renmaing purpose
							try:
								rename_typedef_refid_to_name[component_dict["@refid"]] = component_dict["name"]
							except KeyError:
								rename_typedef_refid_to_name[component_dict["@id"]] = component_dict["name"]
					else:
						# TODO: Support remain types
						pass

		# Scan all codelines to find typedefs
		if len(rename_typedef_refid_to_name) > 0:
			found_cnt = 0
			for codeline_dict in module_dict["doxygen"]["compounddef"]["programlisting"]["codeline"]:
				if found_cnt >= len(rename_typedef_refid_to_name):
					break  # early stop if we have found all typedefs
    
				if "@refid" in codeline_dict and codeline_dict["@refid"] in rename_typedef_refid_to_name:
					if isinstance(codeline_dict["highlight"], dict):
						# Ignored for now, tricky to handle
						print(f"Unexpected dict type in highlight: {codeline_dict['highlight']}, codeline_dict={codeline_dict}")
						found_cnt += 1
					elif isinstance(codeline_dict["highlight"], List):
						for data in codeline_dict["highlight"]:
							if "@class" in data and data["@class"] == "keyword":
								assert data["#text"] in {"typedef", "struct", "class"}
							if "@class" in data and data["@class"] == "keywordtype":
								# Ignored, since they are types like "int", "void", etc.
								# e.g., typedef int my_int;
								found_cnt += 1
								break
							if "ref" in data:  # 
								found_cnt += 1
								try:
									old_ref = data["ref"][0]["@refid"]
									old_name = data["ref"][0]["#text"]
								except KeyError:
									# Corner case, ignored for now
									print(f"Unexpected typedef refid not found in rename dict, codeline_dict={codeline_dict}")
									break

								new_name = rename_typedef_refid_to_name[codeline_dict["@refid"]]
								assert new_name == rename_typedef_refid_to_name[codeline_dict["@refid"]]
								# print(f"Found typedef: {new_name} -> {old_ref}, old name: {old_name}")
								self.typedefs.append((old_ref, old_name, new_name))

		self.filename = FilenameInfo()
		self.filename.extract(module_dict["doxygen"]["compounddef"], monitor=monitor, verbose=verbose)

	# Temp use for update existing modules
	def set_filename(self, filename_info):
		self.filename = filename_info

	def get_refid(self):
		return self.refid

	def get_filename(self):
		return self.filename

	def get_classes(self):
		return self.classes

	def get_functions(self):
		return self.functions

	def get_variables(self):
		return self.variables

	def get_all_functions(self):
		# We need: the ref of function info, a new list of functions
		function_infos = [function_info for function_info in self.functions]
		class_infos = self.get_classes()
		for class_info in class_infos:
			function_infos.extend(class_info.get_functions())
		return function_infos

	def read_source_code(self, path_to_project: Union[str, os.PathLike] = None, path_to_xml: Union[str, os.PathLike] = None):
		return self.filename.read_source_code(path_to_project, path_to_xml)

	def dump(self, path_to_output: Union[str, os.PathLike] = None):
		if not os.path.exists(path_to_output):
			os.makedirs(path_to_output, exist_ok=True)
		with open(os.path.join(path_to_output, self.refid), "w") as f:
			f.write("Module name: {}\n".format(self.refid))
			# f.write("Variables: \n")
			# for variable_info in self.variables:
			#     variable_info.dump(f)
			f.write("Functions: \n")
			for function_info in self.functions:
				function_info.dump(f)
			f.write("Classes: \n")
			for class_info in self.classes:
				class_info.dump(f)

	def __hash__(self):
		return hash(self.refid)

	def __eq__(self, other):
		return type(self) == type(other) and self.get_refid() == other.get_refid()
