import os
import copy
import json

import numpy as np

from agentic_analyzer.helper import settings
from agentic_analyzer.formatter.formatter import Formatter


class SourceFormatter(Formatter):

	def store_messages_batches(self):
		if self.messages_batches is None:
			prompt_no = getattr(self.target_config, "STAGE_{}_PROMPT_NO".format(self.stage_id))
			batch_size = getattr(self.target_config, "STAGE_{}_BATCH_SIZE".format(self.stage_id))
			prompt_file = os.path.join(
				settings.global_config.TEMPORARY_PROMPT_PATH, "{}_prompt{}.json".format(self.stage_id.lower(), prompt_no)
			)
			print(prompt_file)
			prompt_file_obj = open(prompt_file, "r")
			prompt = json.load(prompt_file_obj)
			prompt_file_obj.close()
			self.messages_batches = {}
			for batch_index in range(np.ceil(len(self.element_infos) / batch_size).astype(np.int32)):
				for intra_batch_index in range(batch_size):
					function_index = batch_index * batch_size + intra_batch_index
					if function_index < len(self.element_infos):
						if "batch{}".format(batch_index) not in self.messages_batches.keys():
							self.messages_batches["batch{}".format(batch_index)] = copy.deepcopy(prompt)
						self.messages_batches["batch{}".format(batch_index)].extend(
							self._extend_batch_depend_infos(
								batch_index, intra_batch_index, self.element_infos[function_index]
							)
						)

		self._store_messages_batches()

	def _extend_batch_depend_infos(self, batch_index, intra_batch_index, function_info):
		raise NotImplementedError

	def _crop_source_code_lines(self, source_code_lines, start, end):
		if start < 0:
			print("Start line num {} is smaller than 0.".format(start))
			start = 0
		if end > len(source_code_lines) - 1:
			print("End line num {} is larger than {}".format(end, len(source_code_lines) - 1))
			end = len(source_code_lines) - 1
		return source_code_lines[start:(end + 1)]
