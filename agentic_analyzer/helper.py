import os
import shutil
import json
import yaml
import time
from typing import Any, Dict


class EasyDict(dict):
    """Convenience class that behaves like a dict but allows access with the attribute syntax."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        del self[name]


class PromptTemplateInitializer:
    _initialized = False

    @classmethod
    def instantiate_template(cls, system_name, template_path, temporary_path):
        if cls._initialized:
            return

        print("Instantiating prompt template...")
        print("Template path: {}".format(template_path))
        print("Temporary path: {}".format(temporary_path))

        if os.path.exists(temporary_path):
            shutil.rmtree(temporary_path, ignore_errors=False)
        shutil.copytree(template_path, temporary_path)

        for prompt_filename in os.listdir(temporary_path):
            prompt_filepath = os.path.join(temporary_path, prompt_filename)
            if not os.path.isfile(prompt_filepath) or not prompt_filepath.endswith(".json"):
                continue

            # load
            with open(prompt_filepath, "r") as f:
                unformat_prompt = json.load(f)

            # format
            formatted_prompt = unformat_prompt
            for key in unformat_prompt.keys():
                if "{UDF_SYS}" in unformat_prompt[key]:
                    unformat_prompt[key] = unformat_prompt[key].format(UDF_SYS=system_name)

            # write back
            with open(prompt_filepath, "w") as f:
                json.dump(formatted_prompt, f, indent=4)

        cls._initialized = True
        print("Prompt template instantiated.")

def recursive_convert_to_easydict(obj: Dict) -> EasyDict:
    """Recursively convert a dictionary to an EasyDict."""
    if not isinstance(obj, Dict):
        return obj
    for key, value in obj.items():
        if isinstance(value, Dict):
            obj[key] = recursive_convert_to_easydict(value)
    return EasyDict(obj)


def read_config_file(config_path: str) -> EasyDict:
    """Read a YAML configuration file and return its contents as an EasyDict."""
    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)
    for key, value in config_data.items():
        if isinstance(value, Dict):
            config_data[key] = recursive_convert_to_easydict(value)
    return EasyDict(config_data)

def read_all_config_files(config_dir: str) -> EasyDict:
    """Read all YAML configuration files in a directory and return their contents as an EasyDict."""
    all_configs = EasyDict()
    for filename in os.listdir(config_dir):
        if not filename.endswith(".yaml"):
            continue

        config_name = os.path.splitext(filename)[0]
        config_path = os.path.join(config_dir, filename)
        all_configs[config_name] = read_config_file(config_path)
    return all_configs

# Load the configuration file [hardcoded]
_analyzer_project_path = os.path.dirname(os.path.realpath(__file__))  # agentic_analyzer path
_config_path = os.path.join(_analyzer_project_path, "configs")

# Global Config
settings = read_all_config_files(_config_path)

# Post-processing
# Specify the path to the prompt template and the temporary prompt path
if getattr(settings.global_config, "PROJECT_HOME", "auto") == "auto":
    settings.global_config.PROJECT_HOME = _analyzer_project_path  # default to the agentic_analyzer directory

_start_date = time.strftime("%Y%m%d-%H%M", time.localtime())

entrypoint_name = os.environ.get("AGENTIC_ANALYZER_ENTRYPOINT", "default_entrypoint")

# Create output directories if not specified
if entrypoint_name == "doc_tokenizer":
    if getattr(settings.global_config, "PATH_TO_DOC_RESULTS", "auto") == "auto":
        settings.global_config.PATH_TO_DOC_RESULTS = os.path.join(settings.global_config.PROJECT_HOME, "output", entrypoint_name, _start_date)
        print("PATH_TO_DOC_RESULTS not specified, set to {}".format(settings.global_config.PATH_TO_DOC_RESULTS))
        os.makedirs(settings.global_config.PATH_TO_DOC_RESULTS, exist_ok=True)
elif entrypoint_name in ["default_entrypoint", "shared_analyzer", "type_analyzer"]:
    if getattr(settings.global_config, "PATH_TO_DOC_RESULTS", "auto") == "auto":
        raise ValueError(f"\"auto\" for PATH_TO_DOC_RESULTS is not allowed for entrypoint \"{entrypoint_name}\". It must be specified in global_config.")
    
    if getattr(settings.global_config, "PATH_TO_OUTPUT", "auto") == "auto":
        settings.global_config.PATH_TO_OUTPUT = os.path.join(settings.global_config.PROJECT_HOME, "output", entrypoint_name, _start_date)
        print("PATH_TO_OUTPUT not specified, set to {}".format(settings.global_config.PATH_TO_OUTPUT))
        os.makedirs(settings.global_config.PATH_TO_OUTPUT, exist_ok=True)

    if getattr(settings.global_config, "PROMPT_TEMPLATE_PATH", "auto") == "auto":
        settings.global_config.PROMPT_TEMPLATE_PATH = os.path.join(settings.global_config.PROJECT_HOME, "prompts", settings.global_config.PROMPT_VERSION)
        print("PROMPT_TEMPLATE_PATH not specified, set to {}".format(settings.global_config.PROMPT_TEMPLATE_PATH))
        if not os.path.exists(settings.global_config.PROMPT_TEMPLATE_PATH):
            raise FileNotFoundError(f"The prompt path {settings.global_config.PROMPT_TEMPLATE_PATH} does not exist.")

    # settings.global_config.TEMPORARY_PROMPT_PATH is always set to a temp folder in the output dir
    settings.global_config.TEMPORARY_PROMPT_PATH = os.path.join(settings.global_config.PATH_TO_OUTPUT, "prompts")

# Print out the loaded global configuration for verification
def recursive_print_settings(settings: EasyDict, indent: int = 0):
    for key, value in settings.items():
        if isinstance(value, EasyDict):
            print(" " * indent + f"{key}:")
            recursive_print_settings(value, indent + 2)
        else:
            print(" " * indent + f"{key}: {value}")

print("Loaded Global Configuration...")
recursive_print_settings(settings)
