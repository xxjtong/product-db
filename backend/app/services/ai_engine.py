"""Self-contained LLM engine — direct DeepSeek API calls, no Gateway dependency."""
import json
import time
import httpx
from app.config import settings

DEEPSEEK_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class LlmEngine:
    """OpenAI-compatible HTTP client for DeepSeek API."""

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key or settings.AI_GATEWAY_KEY
        self.base_url = base_url or DEEPSEEK_BASE

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages: list, model: str = DEFAULT_MODEL, tools: list = None,
             temperature: float = 0.7, max_tokens: int = 2000, **kwargs) -> dict:
        """Non-streaming chat completion."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if tools:
            payload["tools"] = tools

        resp = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=self._headers(),
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    def chat_stream(self, messages: list, model: str = DEFAULT_MODEL, tools: list = None,
                    temperature: float = 0.7, max_tokens: int = 2000, **kwargs):
        """Streaming chat completion — yields SSE chunks."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        if tools:
            payload["tools"] = tools

        with httpx.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=self._headers(),
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        yield {"done": True}
                        return
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        pass

    def simple_chat(self, user_input: str, system_prompt: str = "", model: str = DEFAULT_MODEL) -> str:
        """Quick one-shot chat — returns text response."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_input})
        result = self.chat(messages, model=model)
        return result["choices"][0]["message"]["content"]


# Singleton
engine = LlmEngine()
