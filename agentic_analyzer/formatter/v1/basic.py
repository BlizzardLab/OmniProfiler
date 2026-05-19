from typing import Union, Any, Dict
import os
import json
import copy

from abc import ABC, abstractmethod

class BasicFormatter(ABC):
    def __init__(self, prompt_template_path: Union[str, os.PathLike]):
        if prompt_template_path is not None:
            with open(prompt_template_path, 'r', encoding='utf-8') as f:
                self.prompt = json.load(f)["input"]

    def prompt_gen(self, infos: Any) -> Dict[str, str]:
        prompt_instance = f"{self.prompt_fill(infos)}\n\nOutputs: "
        prompt_dict = {
            "user_input": prompt_instance,
            "instructions": copy.deepcopy(self.prompt)
        }
        return prompt_dict

    @abstractmethod
    def prompt_fill(self, infos: Any) -> str:
        ...