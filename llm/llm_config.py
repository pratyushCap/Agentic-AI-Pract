# llm/llm_config.py
from typing import List, Optional

from openai import OpenAI

from config import config


class LLMClient:
    """
    Wrapper around OpenAI client configured for your Generative Engine.
    Replaces the logic from your original chat.py
    """
    
    def __init__(self):
        self.client = None
        self.model = config.LLM_MODEL
        self.temperature = config.LLM_TEMPERATURE
        self.max_tokens = config.LLM_MAX_TOKENS

        if config.LLM_API_KEY:
            self.client = OpenAI(
                base_url=config.LLM_BASE_URL,
                api_key=config.LLM_API_KEY,
            )
    
    def chat(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[dict]] = None
    ) -> str:
        """
        Make a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Optional override for temperature
            max_tokens: Optional override for max tokens
            tools: Optional list of tool definitions for function calling
        
        Returns:
            Response text content
        """
        if not self.client:
            raise RuntimeError("LLM client is not configured. Set LLM_API_KEY first.")

        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature or self.temperature,
                "max_tokens": max_tokens or self.max_tokens,
            }
            
            if tools and self.model != "amazon.nova-lite-v1:0":
                params["tools"] = tools
                params["tool_choice"] = "auto"
            
            completion = self.client.chat.completions.create(**params)
            
            # Handle tool calls if present
            response_message = completion.choices[0].message
            if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
                return {
                    "type": "tool_call",
                    "tool_calls": response_message.tool_calls,
                    "message": response_message.content
                }
            
            return response_message.content
        
        except Exception as e:
            message = str(e)
            if "Tool Choice" in message or "tool_choice" in message.lower() or "doesn't support" in message:
                try:
                    params.pop("tools", None)
                    params.pop("tool_choice", None)
                    completion = self.client.chat.completions.create(**params)
                    response_message = completion.choices[0].message
                    return response_message.content
                except Exception as fallback_error:
                    raise RuntimeError(f"LLM API error: {str(fallback_error)}")
            raise RuntimeError(f"LLM API error: {message}")
    
    def stream_chat(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ):
        """Generator for streaming responses"""
        if not self.client:
            raise RuntimeError("LLM client is not configured. Set LLM_API_KEY first.")

        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature or self.temperature,
                "max_tokens": max_tokens or self.max_tokens,
                "stream": True
            }
            
            stream = self.client.chat.completions.create(**params)
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        except Exception as e:
            raise RuntimeError(f"LLM streaming error: {str(e)}")

# Create singleton instance
llm_client = LLMClient()