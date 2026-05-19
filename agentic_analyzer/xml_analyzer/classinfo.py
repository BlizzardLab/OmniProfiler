import os
import sys
import json

from typing import Union, Dict, List, Set
import numpy as np

from agentic_analyzer.xml_analyzer.functioninfo import FunctionInfo
from agentic_analyzer.xml_analyzer.variableinfo import VariableInfo
from agentic_analyzer.xml_analyzer.descriptioninfo import DescriptionInfo

import agentic_analyzer.xml_analyzer.utils as utils


class ClassInfo():
	def __init__(self):
		self.refid = None

		self.public_functions = []
		self.private_functions = []

		self.public_datas = []
		self.private_datas = []

		self.name = None
		self.description = None
		self.location = None

	def __add_component(self, type, component):
		if type == "public_function":
			self.public_functions.append(component)
		elif type == "private_function" or type == "protected_function":
			self.private_functions.append(component)
		elif type == "public_variable":
			self.public_datas.append(component)
		elif type == "private_variable" or type == "protected_variable":
			self.private_datas.append(component)
		else:
			return

	def __get_member_definition(self, refid: str, class_dict: Dict, monitor: utils.Monitor = None, verbose: bool = False):
		member_definitions = []
		sections = []
		if isinstance(class_dict["doxygen"]["compounddef"]["sectiondef"], Dict):
			sections.append(class_dict["doxygen"]["compounddef"]["sectiondef"])
		elif isinstance(class_dict["doxygen"]["compounddef"]["sectiondef"], List):
			sections.extend(class_dict["doxygen"]["compounddef"]["sectiondef"])

		for section in sections:
			try:
				query_key = "memberdef" if "memberdef" in section else "member"
				if isinstance(section[query_key], List):
					member_definitions.extend(section[query_key])
				elif isinstance(section[query_key], Dict):
					member_definitions.append(section[query_key])
			except KeyError:
				monitor.log(utils.AnomonyType.KEY_MISSING, utils.ComponentType.CLASS, self.refid, f"Unavailable key when looking up {refid}")
		return member_definitions

	def __get_component_definition(self, refid: str, path_to_xml: Union[str, os.PathLike] = None, monitor: utils.Monitor = None, verbose: bool = False):
		class_name = "_".join(refid.split("_")[:-1])
		class_dict = utils.load_xml(os.path.join(path_to_xml, f"{class_name}.xml"))

		if class_dict is None:
			monitor.log(utils.AnomonyType.NO_FILE, utils.ComponentType.CLASS, refid, f"Class XML not found for {class_name}")
			return None
  
		member_definitions = self.__get_member_definition(refid, class_dict, monitor, verbose)
		target_definition = None
		for member_definition in member_definitions:
			if member_definition is None:
				monitor.log(utils.AnomonyType.UNEXPECTED_NONE_VALUE, utils.ComponentType.UNKNOWN, refid, f"Unexpected None member definition in class {class_name}")
				continue

			if not isinstance(member_definition, Dict):
				monitor.log(utils.AnomonyType.UNEXPECTED_TYPE, utils.ComponentType.UNKNOWN, refid, f"Unexpected member definition type {type(member_definition)} in class {class_name}")
				continue

			query_key = "@id" if "@id" in member_definition else "@refid"
			if member_definition[query_key] == refid:
				target_definition = member_definition
				break
		return target_definition

	def read_source_code(self, path_to_xml: Union[str, os.PathLike] = None):
		output_source_code_lines = []
		if self.location is not None:
			source_code_file = os.path.join(path_to_xml, self.location["file"])
			source_code_obj = utils.read_file_obj(source_code_file)
			# print("Reading source code from {}".format(source_code_file))
			source_code_lines = source_code_obj.readlines()
			source_code_obj.close()
			output_source_code_lines = source_code_lines[int(self.location["start"]) - 1:int(self.location["end"])]
		return output_source_code_lines

	def read_source_code_with_line_number(self, path_to_xml: Union[str, os.PathLike] = None):
		class_source_code_lines = self.read_source_code(path_to_xml)
		for line_num in range(len(class_source_code_lines)):
			class_source_code_lines[line_num] = f"{line_num}. {class_source_code_lines[line_num]}"
		return class_source_code_lines

	def load(self, refid: str, path_to_xml: Union[str, os.PathLike], enumvalue_refids: Set, monitor: utils.Monitor = None, verbose: bool = False):
		self.refid = refid

		class_file = os.path.join(path_to_xml, f"{refid}.xml")
		class_dict = utils.load_xml(class_file)

		# Try get metadata
		component_metadatas = None
		try:
			component_metadatas = class_dict["doxygen"]["compounddef"]["listofallmembers"]["member"]
		except TypeError as e:
			monitor.log(utils.AnomonyType.NO_METADATA, utils.ComponentType.CLASS, refid, "No component metadata")
			return

		for component_metadata in np.array([component_metadatas]).flatten():
			# exclude all enumvalue
			if component_metadata["@refid"] in enumvalue_refids:
				continue

			component_definition = self.__get_component_definition(component_metadata["@refid"], path_to_xml, monitor, verbose)
			if component_definition is None:
				monitor.log(utils.AnomonyType.NO_METADATA, utils.ComponentType.CLASS, refid,
							f"No component definition found for member {component_metadata['@refid']}")
				if verbose:
					print(f"No component definition found for member {component_metadata['@refid']} in class {refid}")
			else:
				component_obj = None
				if component_definition["@kind"] == "function":
					try:
						component_obj = FunctionInfo()
						component_obj.extract(component_definition, monitor, verbose=verbose)
					except AssertionError:  # undefined function
						component_obj = None
				elif component_definition["@kind"] == "variable":
					component_obj = VariableInfo()
					component_obj.extract(component_definition, monitor, verbose=verbose)
				else:
					monitor.log(utils.AnomonyType.IGNORED, utils.ComponentType.CLASS, refid,
								f"{component_metadata['@refid']} for {component_definition['@kind']} in class {refid}")
					if verbose:
						print(f"Unexpected component kind {component_definition['@kind']} in class {refid}")

				if component_obj is not None:
					self.__add_component(
						f"{component_definition['@prot']}_{component_definition['@kind']}", component_obj
					)

		self.name = class_dict["doxygen"]["compounddef"]["compoundname"]
		self.description = DescriptionInfo()
		self.description.extract_all({
			"briefdescription": class_dict["doxygen"]["compounddef"]["briefdescription"],
			"detaileddescription": class_dict["doxygen"]["compounddef"]["detaileddescription"]
		}, monitor=monitor, verbose=verbose)

		try:
			self.location = {
				"file": class_dict["doxygen"]["compounddef"]["location"]["@bodyfile"],
				"start": class_dict["doxygen"]["compounddef"]["location"]["@bodystart"],
				"end": class_dict["doxygen"]["compounddef"]["location"]["@bodyend"]
			}
		except KeyError:
			monitor.log(utils.AnomonyType.KEY_MISSING, utils.ComponentType.CLASS, self.refid, "Location information missing in class definition")
			if verbose:
				print("============================= Unextracted Class Body Start =============================") 
				print(f"At class {self.name}, id {self.refid}")
				print(class_dict["doxygen"]["compounddef"]["location"])
				print("============================= Unextracted Class Body End =============================") 
			# raise AssertionError("Undefined function {}, id: {}".format(self.name, self.refid))

	def get_functions(self):
		return self.public_functions + self.private_functions

	def get_refid(self):
		return self.refid

	def get_name(self):
		return self.name

	def get_description(self):
		return self.description

	def definition_dumps(self):
		return "{}\n".format(self.name)

	def dump_full(self, f=sys.stdout):
		f.write(f"class {self.refid}\n")
		for public_function in self.public_functions:
			public_function.dump(f)
		for private_function in self.private_functions:
			private_function.dump(f)

	def dump(self, f=sys.stdout):
		f.write(f"Name: {self.name}\n")
		if self.description is not None:
			self.description.dump(f)
		else:
			f.write("\tDescription:\n")

	def __hash__(self):
		return hash(self.refid)

	def __eq__(self, other):
		return type(self) == type(other) and self.get_refid() == other.get_refid()
