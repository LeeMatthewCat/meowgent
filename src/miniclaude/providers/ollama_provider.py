from .base import ToolCall, LLMResponse, LLMProvider
from typing import Optional
import ollama
from rich.console import Console
from rich.markdown import Markdown
from tool import TOOL_REGISTRY
from rich.live import Live
import time

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
            tools=tools_list,
            think=True
        )

        # ========== C. 兩條路線 ==========
        tool_calls = []
        result_full_text = "🤖 "
        think = False
        thing_time = None
        thing_full_text = "💭 "

        console = Console() # 初始化 rich 終端
        with Live(console=console, refresh_per_second=10, vertical_overflow="visible") as live:
            for chunk in response:
                # ----- 1. 流式輸出文字 -----
                if not chunk.message.tool_calls:
                    chunk_text = chunk.message.content
                    thing_chunk_text = getattr(chunk.message, "thinking", None) # 有 chunk.message.thinking 否則為 None

                    if thing_chunk_text: # 推理過程
                        if thing_time is None:
                            thing_time = time.perf_counter() # 計時
                        think = True
                        thing_full_text += thing_chunk_text

                        live.update(Markdown(thing_full_text))

                    if chunk.message.content: # 正式回答
                        if think:
                            thing_time = round(time.perf_counter() - thing_time, 1) # 更新計時，只保留小數點第一位
                            console.print(f"💭 [bold blue]已思考 {thing_time} 秒...[/bold blue]")
                            think = False

                        result_full_text += chunk_text

                        live.update(Markdown(result_full_text))  

                # ----- 2. tool use -----
                else:
                    for f in chunk.message.tool_calls:
                        tool_calls.append(ToolCall(f.function.name, dict(f.function.arguments)))
                    

        # 按照 LLMResponse 的要求輸出
        if tool_calls:
            return LLMResponse(tool_calls=tool_calls)
        else:
            return LLMResponse(content=result_full_text)