import os
import sys
from typing import Union

import agentic_analyzer.xml_analyzer.utils as utils
from agentic_analyzer.xml_analyzer.descriptioninfo import DescriptionInfo


class FilenameInfo:

	def __init__(self):
		self.refid = None
		self.filename = None
		self.description = None

	def extract(self, filename_dict, monitor: utils.Monitor, verbose: bool = False):
		self.refid = filename_dict["@id"]
		self.filename = filename_dict["compoundname"]
		try:
			self.description = DescriptionInfo()
			self.description.extract_all({
				"briefdescription": filename_dict["briefdescription"],
				"detaileddescription": filename_dict["detaileddescription"]
			}, monitor=monitor, verbose=verbose)
		except KeyError:
			print(f"{self.refid} {filename_dict.keys()}")

	def enrich_description(self, description_dict, monitor: utils.Monitor, verbose: bool = False):
		self.description.extract_all(description_dict, monitor=monitor, verbose=verbose)

	def dump(self, f=sys.stdout):
		f.write(f"File Name: {self.filename}\n")

		self.description.dump(f)
		f.write("========\n")

	def get_refid(self):
		return self.refid

	def get_filename(self):
		return self.filename

	def get_name(self):
		return self.get_filename()

	def definition_dumps(self):
		return self.get_filename()

	def read_source_code(self, path_to_project: Union[str, os.PathLike], path_to_xml: Union[str, os.PathLike]):
		module_dict = utils.load_xml(os.path.join(path_to_xml, f"{self.refid}.xml"))
		source_code_lines = []
		if "location" in module_dict["doxygen"]["compounddef"]:
			file_path = module_dict["doxygen"]["compounddef"]["location"]["@file"]
			source_code_file = os.path.join(path_to_project, file_path)
			source_code_obj = utils.read_file_obj(source_code_file)
			source_code_lines = source_code_obj.readlines()
			source_code_obj.close()
		return source_code_lines

	def __eq__(self, o):
		if isinstance(o, FilenameInfo):
			return self.refid == o.refid
		return NotImplemented

	def __ne__(self, o):
		x = self.__eq__(o)
		if x is NotImplemented:
			return NotImplemented
		return not x

	def __hash__(self):
		return hash(self.refid)
