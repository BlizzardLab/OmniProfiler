import copy

from agentic_analyzer.gptquerier.gptquerier import GPTQuerier


class ElemApiQuerier(GPTQuerier):

	def __init__(self, elem_api_formatter, target_config, query_result_template=None):
		self._set_up_query_result = lambda : copy.deepcopy(query_result_template) if query_result_template is not None else {"YES": [], "NEED_DEF": [], "NO": []}

		super().__init__(elem_api_formatter, target_config)

		print("Your api analyzer is ready!")

	def _is_illegal_reply(self, reply, element_infos):
		if reply is None:
			return True
		reply_lines = reply.splitlines()
		if len(reply_lines) != len(element_infos):
			return True
		for reply_line in reply_lines:
			if ":" not in reply_line or reply_line.split(":")[1].strip().upper() not in self.query_data.get_query_output().keys():
				return True
		return False

	def _process_reply(self, reply, element_infos):
		def __inner_process_reply(query_result):
			reply_lines = reply.splitlines()
			for index, reply_line in enumerate(reply_lines):
				query_result[reply_line.split(":")[1].strip().upper()].append(element_infos[index])

		self.query_data.update_query_output(__inner_process_reply)

	@staticmethod
	def merge_query_results(query_results_a, query_results_b):
		merged_query_results = copy.deepcopy(query_results_a)
		for key in query_results_b.keys():
			merged_query_results[key] = list(set(query_results_a[key] + query_results_b[key]))
		return merged_query_results
