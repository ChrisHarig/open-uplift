"""Unified LLM client supporting multiple providers."""

import json
from dataclasses import dataclass


# Base URLs for OpenAI-compatible providers
PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
}

# Approximate pricing per million tokens (USD)
MODEL_PRICING = {
    # Anthropic
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    # OpenAI
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o3-mini": (1.10, 4.40),
}


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    cost_usd: float


class LLMClient:
    """Multi-provider LLM client."""

    def __init__(self, provider: str, model: str, api_key: str, base_url: str | None = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        response_format: str | None = None,
    ) -> LLMResponse:
        if self.provider == "anthropic":
            return self._anthropic_complete(
                system_prompt, user_prompt, max_tokens, temperature
            )
        else:
            # All non-Anthropic providers use OpenAI-compatible API
            return self._openai_complete(
                system_prompt, user_prompt, max_tokens, temperature, response_format
            )

    def complete_with_tool(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_name: str,
        tool_description: str,
        tool_schema: dict,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Call the model and force it to invoke a single named tool.

        Returns LLMResponse where `content` is the JSON-stringified tool input dict.
        Only anthropic and openai providers are supported — Amy-style prompts
        depend on tool-use, which other providers don't expose uniformly.
        """
        if self.provider == "anthropic":
            return self._anthropic_tool(
                system_prompt, user_prompt, tool_name, tool_description, tool_schema, max_tokens, temperature
            )
        elif self.provider == "openai":
            return self._openai_tool(
                system_prompt, user_prompt, tool_name, tool_description, tool_schema, max_tokens, temperature
            )
        else:
            raise NotImplementedError(
                f"complete_with_tool is only supported for anthropic and openai (got {self.provider!r}). "
                "Tool-using prompts cannot run on this provider."
            )

    def _anthropic_tool(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_name: str,
        tool_description: str,
        tool_schema: dict,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            tools=[{"name": tool_name, "description": tool_description, "input_schema": tool_schema}],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user_prompt}],
        )
        tool_input: dict | None = None
        for block in response.content or []:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
                tool_input = block.input
                break
        if tool_input is None:
            raise RuntimeError(f"Anthropic response did not invoke tool {tool_name!r}")
        content = json.dumps(tool_input)
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._estimate_cost(input_tokens, output_tokens)
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            cost_usd=cost,
        )

    def _openai_tool(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_name: str,
        tool_description: str,
        tool_schema: dict,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import openai

        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=[{"type": "function", "function": {"name": tool_name, "description": tool_description, "parameters": tool_schema}}],
            tool_choice={"type": "function", "function": {"name": tool_name}},
        )
        choice = response.choices[0]
        tool_calls = choice.message.tool_calls or []
        if not tool_calls:
            raise RuntimeError(f"OpenAI response did not invoke tool {tool_name!r}")
        arguments = tool_calls[0].function.arguments  # already JSON string
        content = arguments
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = self._estimate_cost(input_tokens, output_tokens)
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            cost_usd=cost,
        )

    def test_connection(self) -> bool:
        """Make a minimal API call to validate the key."""
        try:
            self.complete("You are a test.", "Say 'ok'.", max_tokens=10, temperature=0.0)
            return True
        except Exception:
            return False

    def _anthropic_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._estimate_cost(input_tokens, output_tokens)
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            cost_usd=cost,
        )

    def _openai_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        response_format: str | None,
    ) -> LLMResponse:
        import openai

        base_url = self.base_url or PROVIDER_BASE_URLS.get(self.provider)
        client = openai.OpenAI(api_key=self.api_key, base_url=base_url)
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = self._estimate_cost(input_tokens, output_tokens)
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            cost_usd=cost,
        )

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING.get(self.model)
        if not pricing:
            # Try prefix match
            for model_key, prices in MODEL_PRICING.items():
                if self.model.startswith(model_key):
                    pricing = prices
                    break
        if not pricing:
            return 0.0
        input_price, output_price = pricing
        cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
        return round(cost, 6)
