import sys
from typing import Dict

from agentic_analyzer.xml_analyzer.descriptioninfo import DescriptionInfo
import agentic_analyzer.xml_analyzer.utils as utils


class VariableInfo:

	def __init__(self):
		self.name = None
		self.type = None
		self.description = None
		self.inherit = "N/A"

	def __set_name(self, name):
		self.name = name

	def __set_type(self, type):
		self.type = type

	def __set_description(self, description):
		self.description = description

	def __set_inherit(self, inherit):
		self.inherit = inherit

	def extract(self, variable_dict: Dict, monitor: utils.Monitor, verbose: bool = False):
		if "qualifiedname" in variable_dict.keys():
			self.name = variable_dict["qualifiedname"]
		else:
			self.name = variable_dict["name"]

		if variable_dict["definition"] is None:
			self.type = "unknown"
			if verbose:
				print(f"Warning: {self.name} has no definition")
		else:
			self.type = variable_dict["definition"].replace(self.name, "")

		self.description = DescriptionInfo()
		self.description.extract_all({
			"briefdescription": variable_dict["detaileddescription"],
			"detaileddescription": variable_dict["detaileddescription"]
		}, monitor=monitor, verbose=verbose)

	def field_data_dumps(self):
		return f"{self.name},{self.type},{self.inherit},{self.description}"

	def definition_dumps(self):
		return f"{self.type} {self.name}"

	def dump(self, f=sys.stdout):
		f.write(f"\tName: {self.name}\n")
		f.write(f"\tType: {self.type}\n")
		f.write(f"\tInherit: {self.inherit}\n")
		self.description.dump(f)

		f.write("========\n")

	@staticmethod
	def field_name_dumps():
		return "name,type,inherit,description"
