from typing import Any, Dict, Optional, List, Tuple, Literal
from abc import ABC, abstractmethod
import asyncio
import anthropic
import openai
import backoff

class BasicSession(ABC):
	def __init__(self, api_key: str, model: str, provider: Literal["openai", "anthropic"], valid_reply_set: List[str],
              	 allow_multiple_indicators: bool = False, max_concurrency: int = 6):
		self.sema = asyncio.Semaphore(max_concurrency)
		self.provider = provider
		if provider == "openai":
			self.client = openai.AsyncOpenAI(
					timeout=30.0,
					api_key=api_key,
				)
		elif provider == "anthropic":
			self.client = anthropic.AsyncAnthropic(
					timeout=30.0,
					api_key=api_key,
					http_client=anthropic.DefaultAioHttpClient(),
				)
		else:
			raise ValueError(f"Unsupported provider: {provider}")
		self.model = model
		self.valid_reply_set = valid_reply_set
		self.allow_multiple_indicators = allow_multiple_indicators

		self.stats_lock = asyncio.Lock()
		self.usage_stats = {
			"input_tokens": 0,
			"cached_input_tokens": 0,
			"output_tokens": 0,
			"num_requests": 0,
			"num_successful_requests": 0,
			"num_failed_requests": 0
		}

	def _is_illegal_reply(self, reply: str, metadata: str) -> Tuple[bool, Optional[Dict[str, str]]]:
		if reply is None:
			return True, None
		reply_lines = reply.splitlines()

		# metadata: "type1,type2,..."
		involved_type_names = [t.strip() for t in metadata.split(",")]
		if len(reply_lines) != len(involved_type_names):
			return True, None

		parsed_results = {}
		for reply_line in reply_lines:
			if ":" not in reply_line:
				return True, None

			resource_type_in_reply = reply_line.split(":")[0].strip()
			reply_flags = reply_line.split(":")[1].strip().upper() # may be multiple indicators separated by comma
			if resource_type_in_reply not in involved_type_names:
				return True, None

			if not self.allow_multiple_indicators and "," in reply_flags:
				return True, None
			if not all([flag.strip() in self.valid_reply_set for flag in reply_flags.split(",")]):
				return True, None
			parsed_results[resource_type_in_reply] = reply_flags
		return False, parsed_results

	@backoff.on_exception(backoff.expo, openai.RateLimitError, max_tries=5)
	async def do_query(self,
            		   prompt: Dict[str, str],
                 	   top_p: float = 0.8,
                 	   max_output_tokens: int = 256) -> str:
		# Make the API call to get the response
		async with self.stats_lock:
			self.usage_stats["num_requests"] += 1

		if self.provider == "openai":
			response = await self.client.responses.create(
				model=self.model,
				input=prompt["user_input"],
				instructions=prompt["instructions"],
				top_p=top_p,
				max_output_tokens=max_output_tokens,
			)
			async with self.stats_lock:
				self.usage_stats["input_tokens"] += response.usage.input_tokens
				self.usage_stats["output_tokens"] += response.usage.output_tokens
				self.usage_stats["cached_input_tokens"] += response.usage.input_tokens_details.cached_tokens
			return response.output[0].content[0].text
		elif self.provider == "anthropic":
			response = await self.client.messages.create(
				model=self.model,
				messages=[{"role": "user", "content": prompt["user_input"]}],
				system=[
					{
						"type": "text",
						"text": prompt["instructions"],
						"cache_control": { "type": "ephemeral" }
					}
				],
				top_p=top_p,
				max_tokens=max_output_tokens,
			)
			return response.content[0].text
		else:
			raise ValueError(f"Unsupported provider: {self.provider}")

	async def step(self, prompt: Dict[str, str], metadata: Any, arg: Any) -> Optional[Any]:
		async with self.sema:
			reply = await self.do_query(prompt)
		is_illegal, parsed_result = self._is_illegal_reply(reply, metadata)

		async with self.stats_lock:
			if is_illegal:
				self.usage_stats["num_failed_requests"] += 1
			else:
				self.usage_stats["num_successful_requests"] += 1

		if is_illegal:
			print(f"Received illegal reply: {reply} for metadata: {metadata}")
			return None, arg
    
		return parsed_result, arg
