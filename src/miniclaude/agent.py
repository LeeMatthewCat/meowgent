import os
from google import genai
import ollama
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from tool import execute_tool, TOOL_REGISTRY
from providers.base import ToolCall
from providers.base import LLMProvider, LLMResponse
from typing import List, Callable, Optional, Iterator
import time

class Agent():
    def __init__(self, provider: LLMProvider):
        self.provider = provider # 直接傳入 provider = OllamaProvider(model_name)
        self.history_messages = []
        
    def chat(self, user_input: str, tool_approval: Callable[[str], bool]) -> Iterator[LLMResponse]:
        
        self.history_messages.append(
            {
                "role": "user",
                "content": user_input
            }
        ) # 使用者輸入加入多輪

        while True: # 模型內迴圈
            # 使用者輸入，模型多次調用
            
            # ----- 1. 初始化 -----
            response = self.provider.stream_generate(history_messages=self.history_messages)
            
            thinking_full_text = ""
            result_full_text = ""

            is_thinking = False
            think_start_time = None

            tools: List[ToolCall] = []

            def thinking_finish() -> Optional[LLMResponse]:
                """ 判斷推理階段是否結束，若結束則清除版面並顯示推理時間 """
                nonlocal is_thinking, think_start_time

                if is_thinking: # 表示為推理結束後進到回答或工具調用階段

                    think_time = round(time.perf_counter() - think_start_time, 1) # 更新計時

                    think_start_time = None
                    is_thinking = False

                    return LLMResponse(status="thinking_done", think_time=think_time)

                return None

            for chunk in response:
            
                if chunk.thinking_chunk:
                    is_thinking = True
                    think_start_time = time.perf_counter() if think_start_time is None else think_start_time # 如果沒開始計時（此次推理第一個 token 出現時）開始計時

                    # 流式輸出
                    thinking_full_text += chunk.thinking_chunk
                    yield LLMResponse(status="thinking", content=thinking_full_text)

                if chunk.content_chunk:
                    thinking_status = thinking_finish()
                    if thinking_status:
                        yield thinking_status

                    # 流式輸出
                    result_full_text += chunk.content_chunk
                    yield LLMResponse(status="response", content=result_full_text)

                if chunk.tool_calls:
                    thinking_status = thinking_finish()
                    if thinking_status:
                        yield thinking_status

                    tools.extend(chunk.tool_calls) # 把函數名和參數扁平的傳入（讓傳入的串列扁平化，不要 tools 的串列包 chunk.tool_call 的串列）
                    break # 拿到工具調用後立即退出（不用跑完下方 if tools）

            if tools: # 表示有 tool use 需求
            
                self.history_messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "name": t.tool_name,
                                "args": t.args,
                                "id": getattr(t, "id", None),
                                "thought_signature": getattr(t, "thought_signature", None)
                            } for t in tools
                        ]
                    }
                ) # 呼叫工具的訊息加入多輪

                for t in tools:
                    # t 為 ToolCall 型別物件 
                    
                    need_approval = getattr(TOOL_REGISTRY.get(t.tool_name, None), "need_approval", True)

                    if not need_approval or tool_approval(t.tool_name): # 工具不需要許可或請求許可被同意
                        # tool_approval 是函數
                        self.history_messages.append(
                            {
                                "role": "tool",
                                "tool_name": t.tool_name,
                                "id": getattr(t, "id", None),
                                "content": execute_tool(tool_name=t.tool_name, tool_args=t.args)
                            }
                        ) # 成功調用工具的訊息加入多輪

                        yield LLMResponse(status="tool_executed", tool_name=t.tool_name)
                    else:
                        self.history_messages.append(
                            {
                                "role": "tool",
                                "tool_name": t.tool_name,
                                "id": getattr(t, "id", None),
                                "content": f"User rejected execution of this tool for security reasons"
                            }
                        ) # 工具調用失敗的訊息加入多輪

                        yield LLMResponse(status="tool_rejected", tool_name=t.tool_name)

            else: # 沒有 tool use 需求
                 
                if not result_full_text.strip():
                    result_full_text = "（模型沒有回傳內容）"
                
                self.history_messages.append(
                    {
                        "role": "assistant",
                        "content": result_full_text
                    }
                ) # 對話加入多輪

                break # 模型沒有調用工具 -> 表示已經生成最終回答，故退出 while True: 迴圈