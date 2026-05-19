import os
import sys
import re

from typing import Union, Dict, List

import numpy as np

import agentic_analyzer.xml_analyzer.utils as utils

from agentic_analyzer.xml_analyzer.paraminfo import ParamInfo
from agentic_analyzer.xml_analyzer.descriptioninfo import DescriptionInfo


class FunctionInfo:

	def __init__(self):
		# Infos processed from source code
		self.refid = None
		self.name = None
		self.rettype = None
		self.description: DescriptionInfo = None
		self.params: List[ParamInfo] = []
		self.attributes: List[str] = []
		self.inherit = "N/A"
		self.location = None

		# Infos added during type_analyzer
		self.class_member_of = None  # class name if it's a member function

		# Infos added during analyzing
		self.sync_sec = None
		self.exec_time = None
		self.invoke_freq = None
		self.loop_cond = None
		self.lock_op = None

	def __set_name(self, name):
		self.name = name

	def __set_rettype(self, rettype):
		self.rettype = rettype

	def __set_description(self, description):
		self.description = description

	def __set_inherit(self, inherit):
		self.inherit = inherit

	def __add_param(self, type, name):
		self.params.append((type, name))

	def __add_attribute(self, attribute):
		self.attributes.append(attribute)

	def set_sync_sec(self, sync_sec):
		try:
			if self.sync_sec is None:
				self.sync_sec = sync_sec
		except AttributeError:
			self.sync_sec = sync_sec

	def set_exec_time(self, exec_time):
		try:
			if self.exec_time is None:
				self.exec_time = exec_time
		except AttributeError:
			self.exec_time = exec_time

	def set_invoke_freq(self, invoke_freq):
		try:
			if self.invoke_freq is None:
				self.invoke_freq = invoke_freq
		except AttributeError:
			self.invoke_freq = invoke_freq

	def set_loop_cond(self, loop_cond):
		loop_cond_str = str(loop_cond)
		try:
			if self.loop_cond is None:
				self.loop_cond = loop_cond_str
		except AttributeError:
			self.loop_cond = loop_cond_str

	def set_lock_op(self, lock_op):
		try:
			if self.lock_op is None:
				self.lock_op = lock_op
		except AttributeError:
			self.lock_op = lock_op

	def get_refid(self):
		return self.refid

	def get_name(self):
		return self.name

	def get_rettype(self):
		return self.rettype

	def get_params(self):
		return self.params

	def get_params_str(self):
		return [f"{param.get_type()} {param.get_name()}" for param in self.params]

	def get_attributes(self):
		return self.attributes

	def get_location(self):
		return self.location

	def get_sync_sec(self):
		return self.sync_sec

	def get_exec_time(self):
		return self.exec_time

	def get_invoke_freq(self):
		return self.invoke_freq

	def get_loop_cond(self):
		return self.loop_cond

	def get_lock_op(self):
		return self.lock_op

	def read_source_code(self, path_to_project: Union[str, os.PathLike] = None):
		source_code_file = os.path.join(path_to_project, self.location["file"])
		source_code_obj = utils.read_file_obj(source_code_file)
		source_code_lines = source_code_obj.readlines()
		source_code_obj.close()
		return source_code_lines[int(self.location["start"]) - 1:int(self.location["end"])]

	def read_source_code_with_line_number(self, path_to_project: Union[str, os.PathLike] = None):
		function_source_code_lines = self.read_source_code(path_to_project)
		for line_num in range(len(function_source_code_lines)):
			function_source_code_lines[line_num] = f"{line_num}. {function_source_code_lines[line_num]}"
		return function_source_code_lines

	def extract(self, func_dict: Dict, monitor: utils.Monitor, verbose: bool = False):
		self.refid = func_dict["@id"]
		if "qualifiedname" in func_dict.keys():
			self.name = func_dict["qualifiedname"]
		else:
			self.name = func_dict["name"]
		self.rettype = func_dict["definition"].replace(self.name, "")  # TODO: buggy here, need better parsing

		try:
			match = re.match(r"\((.*)\)(.*)", func_dict["argsstring"])
			if match:
				_, attribute_str = match.groups()
			else:
				monitor.log(utils.AnomonyType.UNEXPECTED_FORMAT, utils.ComponentType.FUNCTION, self.refid,
								f"Unmatched argsstring: {func_dict['argsstring']}")
				if verbose:
					print(f"Warning: unmatched argsstring: {func_dict['argsstring']}")
				attribute_str = ""
		except TypeError:
			monitor.log(utils.AnomonyType.UNEXPECTED_TYPE, utils.ComponentType.FUNCTION, self.refid,
							f"Unexpected TypeError when processing argsstring: {func_dict['argsstring']}")
			if verbose:
				print(func_dict)
			return

		if "param" in func_dict.keys():
			for param_info_index, param_info_dict in enumerate(np.array(func_dict["param"]).flatten()):
				param_info = ParamInfo()
				param_info.extract(param_info_dict)
				self.params.append(param_info)

		attributes = attribute_str.strip().split(" ")
		for attribute in attributes:
			self.attributes.append(attribute.strip())

		self.description = DescriptionInfo()
		self.description.extract_all({
			"briefdescription": func_dict["briefdescription"],
			"detaileddescription": func_dict["detaileddescription"]
		}, monitor=monitor, verbose=verbose)
  
		try:
			self.location = {
				"file": func_dict["location"]["@bodyfile"],
				"start": func_dict["location"]["@bodystart"],
				"end": func_dict["location"]["@bodyend"]
			}
		except KeyError:
			monitor.log(utils.AnomonyType.NO_DEFINITION, utils.ComponentType.FUNCTION, self.refid,
						f"Location info missing for function {self.name}")
			raise AssertionError(f"Undefined function {self.name}")

	def field_data_dumps(self):
		outputStr = f"{self.name},{self.returnType},"
		for param in self.params:
			outputStr += f"({param[0]} {param[1]});"
		outputStr += ","
		for attribute in self.attributes:
			outputStr += f"{attribute};"
		outputStr += f",{self.inherit},{self.description}"
		return outputStr

	def definition_dumps(self):
		return f"{self.get_rettype()} {self.get_name()}({', '.join(self.get_params_str())}) {' '.join(self.get_attributes())}\n"

	@property
	def ordered_param_str(self):
		param_list = []
		has_this_pointer = getattr(self, "class_member_of", None) is not None
		has_params = False
		if has_this_pointer:
			param_list.append(f"(idx=this: {self.class_member_of}* this)")
		for idx, param in enumerate(self.params):
			param_list.append(f"(idx={idx}: {param.get_type()} {param.get_name()})")

		has_params = len(param_list) > 0
		return "void" if not has_params else ", ".join(param_list)

	def dump(self, f=sys.stdout):
		# f.write("----Start-of-Function----\n")
		f.write(f"Name: {self.name}\n")
		f.write(f"Return Type: {self.rettype}\n")

		f.write(f"Params: {self.ordered_param_str}\n")

		if len(self.description.items) != 0:
			self.description.dump(f)
		# f.write("----End-of-Function----\n")

	def __hash__(self):
		return hash(self.refid)

	def __eq__(self, other):
		return type(self) == type(other) and self.get_refid() == other.get_refid()

	@staticmethod
	def field_name_dumps():
		return "name,returnType,params,attributes,inherit,description"
