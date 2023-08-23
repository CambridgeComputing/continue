import json
from typing import Any, Coroutine, Dict, Generator, List, Union

import aiohttp

from ...core.main import ChatMessage
from ..llm import LLM
from ..util.count_tokens import DEFAULT_ARGS, compile_chat_messages, count_tokens


class Ollama(LLM):
    model: str = "llama2"
    server_url: str = "http://localhost:11434"
    max_context_length: int = 2048

    _client_session: aiohttp.ClientSession = None

    class Config:
        arbitrary_types_allowed = True

    async def start(self, **kwargs):
        self._client_session = aiohttp.ClientSession()

    async def stop(self):
        await self._client_session.close()

    @property
    def name(self):
        return self.model

    @property
    def context_length(self) -> int:
        return self.max_context_length

    @property
    def default_args(self):
        return {**DEFAULT_ARGS, "model": self.name, "max_tokens": 1024}

    def count_tokens(self, text: str):
        return count_tokens(self.name, text)

    def convert_to_chat(self, msgs: ChatMessage) -> str:
        if len(msgs) == 0:
            return ""

        prompt = ""
        has_system = msgs[0]["role"] == "system"
        if has_system:
            system_message = f"""\
                <<SYS>>
                {self.system_message}
                <</SYS>>
                
                """
            if len(msgs) > 1:
                prompt += f"[INST] {system_message}{msgs[1]['content']} [/INST]"
            else:
                prompt += f"[INST] {system_message} [/INST]"
                return

        for i in range(2 if has_system else 0, len(msgs)):
            if msgs[i]["role"] == "user":
                prompt += f"[INST] {msgs[i]['content']} [/INST]"
            else:
                prompt += msgs[i]["content"]

        return prompt

    async def stream_complete(
        self, prompt, with_history: List[ChatMessage] = None, **kwargs
    ) -> Generator[Union[Any, List, Dict], None, None]:
        args = {**self.default_args, **kwargs}
        messages = compile_chat_messages(
            self.name,
            with_history,
            self.context_length,
            args["max_tokens"],
            prompt,
            functions=None,
            system_message=self.system_message,
        )
        prompt = self.convert_to_chat(messages)

        async with self._client_session.post(
            f"{self.server_url}/api/generate",
            json={
                "prompt": prompt,
                "model": self.model,
            },
        ) as resp:
            async for line in resp.content.iter_any():
                if line:
                    try:
                        json_chunk = line.decode("utf-8")
                        chunks = json_chunk.split("\n")
                        for chunk in chunks:
                            if chunk.strip() != "":
                                j = json.loads(chunk)
                                if "response" in j:
                                    yield j["response"]
                    except:
                        raise Exception(str(line[0]))

    async def stream_chat(
        self, messages: List[ChatMessage] = None, **kwargs
    ) -> Generator[Union[Any, List, Dict], None, None]:
        args = {**self.default_args, **kwargs}
        messages = compile_chat_messages(
            self.name,
            messages,
            self.context_length,
            args["max_tokens"],
            None,
            functions=None,
            system_message=self.system_message,
        )
        prompt = self.convert_to_chat(messages)

        async with self._client_session.post(
            f"{self.server_url}/api/generate",
            json={
                "prompt": prompt,
                "model": self.model,
            },
        ) as resp:
            # This is streaming application/json instaed of text/event-stream
            async for line in resp.content.iter_chunks():
                if line[1]:
                    try:
                        json_chunk = line[0].decode("utf-8")
                        chunks = json_chunk.split("\n")
                        for chunk in chunks:
                            if chunk.strip() != "":
                                j = json.loads(chunk)
                                if "response" in j:
                                    yield {
                                        "role": "assistant",
                                        "content": j["response"],
                                    }
                    except:
                        raise Exception(str(line[0]))

    async def complete(
        self, prompt: str, with_history: List[ChatMessage] = None, **kwargs
    ) -> Coroutine[Any, Any, str]:
        completion = ""

        async with self._client_session.post(
            f"{self.server_url}/api/generate",
            json={
                "prompt": prompt,
                "model": self.model,
            },
        ) as resp:
            async for line in resp.content.iter_any():
                if line:
                    try:
                        json_chunk = line.decode("utf-8")
                        chunks = json_chunk.split("\n")
                        for chunk in chunks:
                            if chunk.strip() != "":
                                j = json.loads(chunk)
                                if "response" in j:
                                    completion += j["response"]
                    except:
                        raise Exception(str(line[0]))

        return completion
