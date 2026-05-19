import os
import json
import numpy as np
from copy import deepcopy

from agentic_analyzer.helper import settings
from agentic_analyzer.formatter.formatter import Formatter


# TODO: Func related key words to be replaced
class ApiFormatter(Formatter):

	def __init__(self, element_infos, module_name, target_config, stage_id):
		super().__init__(element_infos, module_name, target_config, stage_id)

	def store_messages_batches(self):
		if self.messages_batches is None:
			prompt_file = os.path.join(
				settings.global_config.TEMPORARY_PROMPT_PATH, "{}_prompt{}.json".format(
					self.stage_id.lower(),
					getattr(self.target_config, "STAGE_{}_PROMPT_NO".format(self.stage_id.upper()))
				)
			)
			with open(prompt_file, "r") as prompt_file_obj:
				prompt = json.load(prompt_file_obj)
			self.messages_batches = {
				"batch{}".format(i): deepcopy(prompt) for i in range(
					np.ceil(
						len(self.element_infos) /
						getattr(self.target_config, "STAGE_{}_BATCH_SIZE".format(self.stage_id.upper()))
					).astype(np.int32)
				)
			}

			class Writer:
				def write(ignored_self, s):
					self.messages_batches["batch{}".format(
						np.floor(
							element_index /
							getattr(self.target_config, "STAGE_{}_BATCH_SIZE".format(self.stage_id.upper()))
						).astype(np.int32)
					)][-1]["content"] += s

			for element_index, element_info in enumerate(self.element_infos):
				self.messages_batches["batch{}".format(
					np.floor(
						element_index /
						getattr(self.target_config, "STAGE_{}_BATCH_SIZE".format(self.stage_id.upper()))
					).astype(np.int32)
				)][-1]["content"] += "{}. ".format(
					element_index % getattr(self.target_config, "STAGE_{}_BATCH_SIZE".format(self.stage_id.upper()))
				)
				element_info.dump(f=Writer())

		self._store_messages_batches()
