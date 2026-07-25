from .base import ToolCall, LLMResponse, LLMProvider
from typing import Optional
from google import genai
from google.genai import types
from tool import TOOL_REGISTRY

class GeminiProvider(LLMProvider):
    def __init__(
        self,
        model_name: str,
    ):
        super().__init__(model_provider="google_gemini", model_name=model_name)

        self.client = genai.Client()

    def generate(self, history_messages: list, tools: Optional[list] = None) -> LLMResponse:

        # ========== A. 格式修改 ==========
        gemini_format = []

        for msg in history_messages:
            role = "model" if msg["role"] == "assistant" else "user"

            gemini_format.append(
                {
                    "role": role,
                    "parts": [
                        {
                            "text": msg["content"]
                        }
                    ]
                }
            )
        
        # ========== B. 工具函數註冊表轉串列 ==========
        tools_list = list(TOOL_REGISTRY.values())

        # ========== C. 遞交給模型 ==========
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=gemini_format,
            config=types.GenerateContentConfig(tools=tools_list)
        )

        # ========== D. 解析調用函數 ==========
        if response.function_calls: # 模型有函數呼叫

            tool_calls = []
            for f in response.function_calls:
                tool_calls.append(ToolCall(f.name, dict(f.args)))

            try:
                content=response.text
            except Exception:
                content = None

            return LLMResponse(content=content, tool_calls=tool_calls)
                
        return LLMResponse(content=response.text)



        
