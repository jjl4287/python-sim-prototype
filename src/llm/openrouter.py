"""OpenRouter API client with function calling support."""

from __future__ import annotations
import os
import json
from enum import Enum
from typing import Any, Optional, AsyncIterator
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

load_dotenv()


class ModelTier(str, Enum):
    """Model tiers for different tasks."""
    ADVISOR = "advisor"      # Cheap, fast, frequent
    ORCHESTRATOR = "orchestrator"  # Smart, rare


@dataclass
class ToolCall:
    """A tool call extracted from model response."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Structured response from LLM."""
    content: Optional[str]
    tool_calls: list[ToolCall]
    finish_reason: str
    model: str
    usage: dict[str, int]
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class OpenRouterClient:
    """Client for OpenRouter API with function calling support."""
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        advisor_model: Optional[str] = None,
        orchestrator_model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        self.advisor_model = advisor_model or os.getenv("ADVISOR_MODEL", "moonshotai/kimi-k2-0905")
        self.orchestrator_model = orchestrator_model or os.getenv("ORCHESTRATOR_MODEL", "google/gemini-3-flash-preview")
        
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/delegative-strategy-game",
                "X-Title": "Delegative Strategy Game",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        
        self._async_client: Optional[httpx.AsyncClient] = None
    
    def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/delegative-strategy-game",
                    "X-Title": "Delegative Strategy Game",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._async_client
    
    def _get_model(self, tier: ModelTier) -> str:
        """Get model name for tier."""
        if tier == ModelTier.ADVISOR:
            return self.advisor_model
        return self.orchestrator_model
    
    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        """Parse API response into structured format."""
        choice = data["choices"][0]
        message = choice["message"]
        
        tool_calls = []
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=tc["function"]["name"],
                    arguments=args,
                ))
        
        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            model=data.get("model", "unknown"),
            usage=data.get("usage", {}),
        )
    
    def chat(
        self,
        messages: list[dict[str, Any]],
        tier: ModelTier = ModelTier.ADVISOR,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Send a chat completion request."""
        model = self._get_model(tier)
        
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        
        response = self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        
        return self._parse_response(response.json())
    
    async def chat_async(
        self,
        messages: list[dict[str, Any]],
        tier: ModelTier = ModelTier.ADVISOR,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Send an async chat completion request."""
        client = self._get_async_client()
        model = self._get_model(tier)
        
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        
        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        
        return self._parse_response(response.json())
    
    def chat_with_structured_output(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        tier: ModelTier = ModelTier.ORCHESTRATOR,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Request structured JSON output matching a schema."""
        model = self._get_model(tier)
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        
        response = self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON from the content
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError(f"Failed to parse JSON from response: {content}")
    
    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tier: ModelTier = ModelTier.ADVISOR,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream a chat completion (returns async iterator of content chunks)."""
        # Note: This is a sync generator that yields chunks
        # For true async streaming, use chat_stream_async
        model = self._get_model(tier)
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        with self._client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except json.JSONDecodeError:
                        continue
    
    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
        if self._async_client:
            # Note: async client should be closed in async context
            pass
    
    async def close_async(self) -> None:
        """Close the async HTTP client."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
    
    def __enter__(self) -> "OpenRouterClient":
        return self
    
    def __exit__(self, *args: Any) -> None:
        self.close()
