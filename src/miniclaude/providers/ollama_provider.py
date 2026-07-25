from .base import ToolCall, LLMResponse, LLMProvider
from typing import Optional
import ollama
from rich.console import Console
from rich.markdown import Markdown
from tool import TOOL_REGISTRY
from rich.live import Live

class OllamaProvider(LLMProvider):
    def __init__(self, model_name: str):
        super().__init__(model_provider="ollama", model_name=model_name)

    def generate(self, history_messages, tools: Optional[list] = None) -> LLMResponse:

        # ========== A. 工具函數註冊表轉串列 ==========
        tools_list = list(TOOL_REGISTRY.values())

        # ========== B. 遞交給模型 ========== 
        response = ollama.chat(
            model=self.model_name,
            messages=history_messages,
            stream=True, # 流式輸出文字
            tools=tools_list
        )

        # ========== C. 兩條路線 ==========
        tool_calls = []
        full_text = ""

        console = Console() # 初始化 rich 終端
        with Live(console=console, refresh_per_second=10, vertical_overflow="visible") as live:
            for chunk in response:
                # ----- 1. tool use -----
                if chunk.message.tool_calls:
                    for f in chunk.message.tool_calls:
                        tool_calls.append(ToolCall(f.function.name, dict(f.function.arguments)))

                # ----- 2.  流式輸出文字 -----
                else:
                    
                    chunk_text = chunk.message.content

                    if chunk.message.content:
                        full_text += chunk_text

                        live.update(Markdown(full_text))
                        # emd="" 不自動換行（預設情況下每一個 print() 後都會換行）
                        # flush=True 立刻印出      

        # 輸出
        if tool_calls:
            return LLMResponse(tool_calls=tool_calls)
        else:
            return LLMResponse(content=full_text)