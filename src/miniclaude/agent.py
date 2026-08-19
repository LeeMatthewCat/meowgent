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
    def __init__(self, provider: LLMProvider, max_turns: int = 20):
        self.provider = provider # 直接傳入 provider = OllamaProvider(model_name)
        self.max_turns = max_turns
        self.history_messages = []
        
    def chat(self, user_input: str, tool_approval: Callable[[str, dict], bool]) -> Iterator[LLMResponse]:
        
        self.history_messages.append(
            {
                "role": "user",
                "content": user_input
            }
        ) # 使用者輸入加入多輪

        turns = 0
        while turns < self.max_turns: # 模型內迴圈，使用者輸入，模型多次調用
            # turns 為 self.max_turns - 1 時表示為最後一次
            
            # ========== A. 初始化、請求模型 ==========
            
            # ----- 對於無限調用的處理 -----
            turns += 1 # 計數 +1

            temp_history_messages = list(self.history_messages) # 複製一份，阻止無限調用訊息進入多輪歷史
            
            if turns == self.max_turns: # 為最後一輪
                temp_history_messages.append(
                    {
                        "role": "user",
                        "content": "[System Prompt] You have reached the maximum tool call limit. Please do not call any more tools, output your final answer directly, and summarize the current progress and encountered issues."
                    }
                )
                available_tools = [] # 不給工具
            else:
                available_tools = None # 不做工具指定時，預設使用全部工具
            # -----

            response = self.provider.stream_generate(
                history_messages=temp_history_messages,
                tools=available_tools
            ) # 請求模型
            
            thinking_full_text = ""
            result_full_text = ""

            is_thinking = False
            think_start_time = None

            tools: List[ToolCall] = [] # 模型要使用的工具

            def thinking_finish() -> Optional[LLMResponse]:
                """ 判斷推理階段是否結束，若結束則清除版面並顯示推理時間 """
                nonlocal is_thinking, think_start_time

                if is_thinking: # 表示為推理結束後進到回答或工具調用階段

                    think_time = round(time.perf_counter() - think_start_time, 1) # 更新計時

                    think_start_time = None
                    is_thinking = False

                    return LLMResponse(status="thinking_done", think_time=think_time)

                return None

            # ========== B. 處理模型回應 ==========
            for chunk in response:
            
                if chunk.thinking_chunk: # 推理
                    is_thinking = True
                    think_start_time = time.perf_counter() if think_start_time is None else think_start_time # 如果沒開始計時（此次推理第一個 token 出現時）開始計時

                    # 流式輸出
                    thinking_full_text += chunk.thinking_chunk
                    yield LLMResponse(status="thinking", content=thinking_full_text)

                if chunk.content_chunk: # 回答
                    thinking_status = thinking_finish()
                    if thinking_status:
                        yield thinking_status

                    # 流式輸出
                    result_full_text += chunk.content_chunk
                    yield LLMResponse(status="response", content=result_full_text)

                if chunk.tool_calls: # 工具調用
                    thinking_status = thinking_finish()
                    if thinking_status:
                        yield thinking_status

                    tools.extend(chunk.tool_calls) # 把函數名和參數扁平的傳入（讓傳入的串列扁平化，不要 tools 的串列包 chunk.tool_call 的串列）

            # ========== C. 工具調用處理 ==========
            if tools: # 表示有 tool use 需求
            
                
                msg = {
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
                # 呼叫工具的訊息加入多輪
                if result_full_text.strip(): # 如果模型調用工具還有輸出文字
                    msg["content"] = result_full_text

                self.history_messages.append(msg)

                for t in tools:
                    # t 為 ToolCall 型別物件 
                    
                    need_approval = getattr(TOOL_REGISTRY.get(t.tool_name, None), "need_approval", True)

                    if not need_approval or tool_approval(t.tool_name, t.args): # 工具不需要許可或請求許可被同意
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