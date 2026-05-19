import sys
from typing import Dict, List

import numpy as np


class ParamInfo:

	def __init__(self):
		self.refid = None
		self.name = None
		self.type = None

	def extract(self, param_dict: Dict):
		self.name = param_dict.get("declname", "")

		type_texts = []
		try:
			self.refid = None

			type_info = param_dict.get("type")
			if isinstance(type_info, Dict) and "ref" in type_info:
				ref_info = type_info["ref"]
				if isinstance(ref_info, Dict):
					self.refid = ref_info.get("@refid")
				elif isinstance(ref_info, List):
					first_ref = ref_info[0]
					if isinstance(first_ref, Dict):
						self.refid = first_ref.get("@refid")
			else:
				self.refid = None
			# self.refid = param_dict["type"]["ref"]["@refid"]
			if "type" in param_dict:
				type_info = param_dict["type"]
				if isinstance(type_info, Dict) and "ref" in type_info:
					for text in np.array(param_dict["type"]["ref"]).flatten():
						type_texts.append(text["#text"])

					self.type = " ".join(type_texts)
				
				# if "#text" in param_dict["type"].keys():
				# 	self.type += " {}".format(param_dict["type"]["#text"])
				type_node = param_dict.get("type")
				if isinstance(type_node, Dict) and "#text" in type_node:
					self.type += " {}".format(type_node["#text"])
				elif isinstance(type_node, str):
					self.type += " {}".format(type_node)
		except TypeError:
			if isinstance(param_dict["type"], str):
				self.refid = ""
				self.type = param_dict["type"]
			else:
				# TODO: Buggy for this case: std::Function<int64(const Message_data)>, to be fixed
				self.refid = ""
				self.type = ""

	def get_refid(self):
		return self.refid

	def get_name(self):
		return self.name if self.name is not None else ""

	def get_type(self):
		return self.type

	def is_base_type(self):
		return self.refid == ""

	def dump(self, f=sys.stdout):
		f.write(f"{self.string},")

	@property
	def string(self):
		return f"{self.type} {self.name}"

	def __eq__(self, other):
		return type(self) == type(other) and self.get_refid() == other.get_refid()

	def __hash__(self):
		return hash(self.refid)
