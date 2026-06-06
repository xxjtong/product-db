"""Self-contained LLM engine — direct DeepSeek API calls, no Gateway dependency."""
import json
import httpx
from app.config import settings

DEEPSEEK_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class LlmEngine:
    """OpenAI-compatible async HTTP client for DeepSeek API."""

    def __init__(self, api_key: str = "", base_url: str = ""):
        self._explicit_key = api_key
        self._cached_key = None
        self.base_url = base_url or DEEPSEEK_BASE

    @property
    def api_key(self) -> str:
        if self._cached_key is None:
            # 1) Explicit key passed to constructor
            if self._explicit_key:
                self._cached_key = self._explicit_key
            else:
                # 2) LLM config primary.api_key from DB
                try:
                    from app.database import SessionLocal
                    from app.models.system_setting import SystemSetting
                    db = SessionLocal()
                    try:
                        s = db.query(SystemSetting).filter_by(key="llm_config").first()
                        if s and s.value:
                            cfg = json.loads(s.value)
                            db_key = cfg.get("primary", {}).get("api_key", "")
                            if db_key:
                                self._cached_key = db_key
                    finally:
                        db.close()
                except Exception:
                    pass
                # 3) Fall back to .env / settings
                if not self._cached_key:
                    self._cached_key = settings.AI_GATEWAY_KEY
        return self._cached_key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(self, messages: list, model: str = DEFAULT_MODEL, tools: list = None,
                   temperature: float = 0.7, max_tokens: int = 2000, **kwargs) -> dict:
        """Non-streaming chat completion (async)."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def chat_stream(self, messages: list, model: str = DEFAULT_MODEL, tools: list = None,
                          temperature: float = 0.7, max_tokens: int = 2000, **kwargs):
        """Streaming chat completion — yields SSE chunks (async)."""
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

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            yield {"done": True}
                            return
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            pass

    async def simple_chat(self, user_input: str, system_prompt: str = "", model: str = DEFAULT_MODEL) -> str:
        """Quick one-shot chat — returns text response."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_input})
        result = await self.chat(messages, model=model)
        return result["choices"][0]["message"]["content"]


# Singleton
engine = LlmEngine()
