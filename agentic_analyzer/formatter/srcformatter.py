from agentic_analyzer.formatter.sourceformatter import SourceFormatter


# TODO: Func related key words to be replaced
# TODO: Name conflict with sourceformatter
class SrcFormatter(SourceFormatter):

	def __init__(self, element_infos, module_name, target_config, stage_id):
		super().__init__(element_infos, module_name, target_config, stage_id)

	def _extend_batch_depend_infos(self, batch_index, intra_batch_index, element_info):
		return [
			{
				"role": "user",
				"content": "".join(self._source_code_formatter(batch_index, intra_batch_index, element_info))
			}
		]

	def _source_code_formatter(self, batch_index, intra_batch_index, element_info):
		element_definitions = []
		element_definitions.append("\n Element ID {}\n".format(intra_batch_index))
		element_definitions.append("\n Element Metadata: \n")
		class Writer:

			def write(ignored_self, s):
				element_definitions.append(s)

		element_info.dump(f=Writer())

		element_definitions.append("\n Element Source Code: \n")
		element_definitions.extend(element_info.read_source_code())
		element_definitions.append("\n//////// Element Seperator ////////\n")
		return element_definitions
