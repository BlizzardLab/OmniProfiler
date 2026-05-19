import sys

from typing import Dict, Union, Iterable

import numpy as np

import agentic_analyzer.xml_analyzer.utils as utils


def get_minor_para_simple(minor_para_content, verbose: bool = False) -> str:
	ret_content = ""
	if isinstance(minor_para_content, str):
		ret_content = minor_para_content
	elif isinstance(minor_para_content, dict):
		try:
			ret_content = minor_para_content["#text"]
		except KeyError:
			# TODO: Fix it
			if verbose:
				print(f"[get_minor_para_simple] To be fixed: {minor_para_content}")
	return ret_content


class DescriptionInfo:

	def __init__(self):
		self.items = []


	def __get_param_items(self, param_dicts: Dict, verbose: bool = False):
		param_items = []
		for param_dict in np.array(param_dicts).flatten():
			if param_dict["@kind"] == "param":
				for param_item_dict in np.array(param_dict["parameteritem"]).flatten():
					param_desc_info = self.ParamDescriptionInfo()
					param_desc_info.extract(param_item_dict, verbose=verbose)
					param_items.append(("param", param_desc_info))
			elif param_dict["@kind"] == "retval":
				retval_desc = self.RetvalDescriptionInfo()
				retval_desc.extract(np.array(param_dict["parameteritem"]).flatten(), verbose=verbose)
				param_items.append(
					("retval", retval_desc)
				)
		return param_items

	def __get_simple_items(self, simple_dict: Dict, verbose: bool = False):
		simple_items = []
		for simple_item_dict in np.array(simple_dict).flatten():
			if simple_item_dict["@kind"] == "return":
				retval_desc = self.RetvalDescriptionInfo()
				retval_desc.extract(np.array(simple_item_dict["para"]).flatten(), verbose=verbose)
				simple_items.append(
					("retval", retval_desc)
				)
			else:
				# Simple fixed
				# TODO: Find a better way if there are more different cases here
				if isinstance(simple_item_dict["para"], dict) and "itemizedlist" in simple_item_dict["para"].keys():
					simple_items.extend(self.__get_itemized_items(simple_item_dict["para"]["itemizedlist"], verbose=verbose))
				else:
					default_desc_info = self.DefaultDescriptionInfo()
					default_desc_info.extract(simple_item_dict["para"], verbose=verbose)
					simple_items.append(
						(simple_item_dict["@kind"], default_desc_info)
					)
		return simple_items

	def __get_itemized_items(self, itemized_dict, verbose: bool = False):
		itemized_items = []
		for one_itemized_dict in np.array([itemized_dict]).flatten():
			for itemized_item in np.array(one_itemized_dict["listitem"]).flatten():
				default_desc_info = self.DefaultDescriptionInfo()
				default_desc_info.extract(get_minor_para_simple(itemized_item["para"], verbose=verbose))
				itemized_items.append(
					("describe", default_desc_info)
				)
		return itemized_items

	def __get_para_items(self, para_dict: Dict, verbose: bool = False):
		para_items = []
		for item_dict in para_dict.items():
			if item_dict[0] == "parameterlist":
				para_items.extend(self.__get_param_items(item_dict[1], verbose=verbose))
			elif item_dict[0] == "simplesect":
				para_items.extend(self.__get_simple_items(item_dict[1], verbose=verbose))
			elif item_dict[0] == "itemizedlist" or item_dict[0] == "orderedlist":
				if item_dict[1] is not None:
					para_items.extend(self.__get_itemized_items(item_dict[1], verbose=verbose))
			elif item_dict[0] == "#text" or item_dict[0] == "heading" or item_dict[0] == "verbatim":
				default_desc_info = self.DefaultDescriptionInfo()
				default_desc_info.extract(item_dict[1], verbose=verbose)
				para_items.append(("describe", default_desc_info))
			elif item_dict[0] == "programlisting":
				# Hard to parse, may be useful
				pass
			elif item_dict[0] == "computeroutput" or item_dict[0] == "emphasis":
				# TODO: Put them into right place
				pass
			elif item_dict[0] == "ndash" or item_dict[0] == "mdash":
				# Ignore it
				# See Binary Log, THD::decide_logging_format
				pass
			elif item_dict[0] == "linebreak" or item_dict[0] == "hruler" or item_dict[0] == "anchor" or item_dict[
				0] == "table" or item_dict[0] == "simplesect" or item_dict[0] == "plantuml" or item_dict[0] == "bold" or item_dict[
				0] == "xrefsect" or item_dict[0] == "xreftitle" or item_dict[0] == "xrefdescription" or item_dict[0] == "lsquo" or item_dict[0] == "rsquo":
				# Ignore it
				# This attribute seem to do nothing good to enrich description
				pass
			elif item_dict[0] == "ulink":
				# Ignore it
				# Currently we don't need external url info
				pass
			elif item_dict[0] == "ref":
				# Ingore it
				# TODO: Put ref content to the blank part in text since there is still useful data in it
				pass
			else:
				if verbose:
					print("============================= Unhandled Description Info Key Start =============================") 
					print(item_dict)
					print("============================= Unhandled Description Info Key End =============================") 
		return para_items

	def extract_all(self, description_dict: Dict, monitor: utils.Monitor, verbose: bool = False):
		if description_dict is not None:
			for description_dict_value in description_dict.values():
				if description_dict_value is not None:
					self.extract(description_dict_value, monitor, verbose=verbose)

	def extract(self, description_dict: Dict, monitor: utils.Monitor, verbose: bool = False):
		processed_description_dict = description_dict
		if "para" not in description_dict.keys():
			if "sect1" in description_dict.keys():
				processed_description_dict = description_dict["sect1"]
		if not isinstance(processed_description_dict, Dict) or "para" not in processed_description_dict.keys():
			monitor.log(utils.AnomonyType.UNEXPECTED_FORMAT, utils.ComponentType.DESCRIPTION, "N/A",
						"DescriptionInfo.extract: Unavailable 'para' key in description_dict")
			if verbose:
				print("============================= Unhandled Key Error Start =============================") 
				print(processed_description_dict)
				print("============================= Unhandled Key Error End =============================") 
		else:
			for description_para in np.array(processed_description_dict["para"]).flatten():
				if isinstance(description_para, str):
					default_desc_info = self.DefaultDescriptionInfo()
					default_desc_info.extract(description_para, verbose=verbose)
					self.items.append(("describe", default_desc_info))
				elif isinstance(description_para, dict):
					self.items.extend(self.__get_para_items(description_para))
				else:
					raise AssertionError(type(description_para))

	def dump(self, f=sys.stdout):
		f.write("Description:\n")
		for item in self.items:
			item[1].dump(f)

	class ParamDescriptionInfo:

		def __init__(self):
			self.name = None
			self.description = []

		def extract(self, param_description_dict: Dict, verbose: bool = False):
			param_name_list = param_description_dict.get("parameternamelist")
			if isinstance(param_name_list, dict):
				self.name = param_name_list.get("parametername")
			else:
				self.name = None

			para_description = param_description_dict.get("parameterdescription", {})
			if isinstance(para_description, dict):
				para_para = para_description.get("para")
			else:
				para_para = None

			if para_para is not None:
				try:
					self.description.append(get_minor_para_simple(para_para))
				except TypeError:
					pass  # Do nothing

		def dump(self, f=sys.stdout):
			f.write(f"\tParameter {self.name}: {' '.join(self.description)}\n")

	class RetvalDescriptionInfo:

		def __init__(self):
			self.retval = ""

		def extract(self, retval_description: Iterable, verbose: bool = False):
			for one_retval_description in retval_description:
				# print(retval_description)
				if isinstance(one_retval_description, Dict):
					try:
						self.retval += "{} {}".format(
							one_retval_description["parameternamelist"]["parametername"],
							get_minor_para_simple(one_retval_description["parameterdescription"]["para"], verbose=verbose)
						)
					except KeyError:
						self.retval += get_minor_para_simple(one_retval_description)
					except TypeError:
						# TODO: Some check to extract as much info as possible
						# None type appeared
						self.retval += ""
				elif isinstance(one_retval_description, str) or isinstance(one_retval_description, np.str_):
					self.retval += str(one_retval_description)
				elif one_retval_description is None:
					if verbose:
						print("[RetvalDescriptionInfo] Unexpected None type for return value description.")
				else:
					print(type(one_retval_description))
					raise AssertionError(one_retval_description)

		def dump(self, f=sys.stdout):
			f.write(f"\tReturn value: {self.retval}\n")

	class DefaultDescriptionInfo:

		def __init__(self):
			self.description = []

		def extract(self, default_description: Union[str, Dict], verbose: bool = False):
			if isinstance(default_description, str):
				self.description.append(default_description)
			elif isinstance(default_description, Dict):
				self.description.append(get_minor_para_simple(default_description, verbose=verbose))
		def dump(self, f=sys.stdout):
			f.write(f"\t{' '.join(self.description)}\n")
