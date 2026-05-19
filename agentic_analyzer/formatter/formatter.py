import os
import json
import pickle

import numpy as np

from agentic_analyzer.helper import settings


class Formatter:

	def __init__(self, element_infos, module_name, target_config, stage_id):
		self.element_infos = element_infos
		self.module_name = module_name
		self.target_config = target_config
		self.stage_id = stage_id
		self.messages_batches = None
		self.element_infos_batches = None

		self.__format_element_infos_batches()

	def _store_messages_batches(self):
		with open(
			os.path.join(
				settings.global_config.PATH_TO_OUTPUT,
				"{}_stage_{}_messages_batches.json".format(self.module_name, self.stage_id.lower())
			), "w"
		) as f:
			json.dump(self.messages_batches, f, indent=2)

	def __format_element_infos_batches(self):
		if self.element_infos_batches is None:
			self.element_infos_batches = {}
			batch_size = getattr(self.target_config, "STAGE_{}_BATCH_SIZE".format(self.stage_id))
			for batch_index in range(np.ceil(len(self.element_infos) / batch_size).astype(np.int32)):
				element_infos_batch = []
				for intra_batch_index in range(batch_size):
					element_index = batch_index * batch_size + intra_batch_index
					if element_index < len(self.element_infos):
						element_infos_batch.append(self.element_infos[element_index])
				if len(element_infos_batch) > 0:
					self.element_infos_batches["batch{}".format(batch_index)] = element_infos_batch

	def store_messages_batches(self):
		raise NotImplementedError

	def store_element_infos_batches(self):
		assert self.element_infos_batches is not None, "Format element info batches first."
		with open(
			os.path.join(
				settings.global_config.PATH_TO_OUTPUT,
				"{}_stage_{}_element_infos_batches.pkl".format(self.module_name, self.stage_id.lower())
			), "wb"
		) as f:
			pickle.dump(self.element_infos_batches, f)

	def load_messages_batches(self):
		with open(
			os.path.join(
				settings.global_config.PATH_TO_OUTPUT,
				"{}_stage_{}_messages_batches.json".format(self.module_name, self.stage_id.lower())
			), "r"
		) as f:
			self.messages_batches = json.load(f)

	def load_element_infos_batches(self):
		with open(
			os.path.join(
				settings.global_config.PATH_TO_OUTPUT,
				"{}_stage_{}_element_infos_batches.pkl".format(self.module_name, self.stage_id.lower())
			), "rb"
		) as f:
			self.element_infos_batches = pickle.load(f)

	def get_messages_batches(self):
		assert self.messages_batches is not None, "Format messages batches first."
		return self.messages_batches

	def get_element_infos_batches(self):
		assert self.element_infos_batches is not None, "Format element info batches first."
		return self.element_infos_batches

	def get_element_infos(self):
		return self.element_infos

	def get_module_name(self):
		return self.module_name

	def get_stage_id(self):
		return self.stage_id

	@staticmethod
	def merge_element_infos(element_infos_a, element_infos_b):
		return list(set(element_infos_a + element_infos_b))
