import os
from google import genai
import ollama
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from tool import execute_tool, TOOL_REGISTRY
from providers.base import ToolCall
from providers.base import LLMProvider, LLMResponse
from typing import List, Callable, Optional, Iterator, Tuple
import time
from concurrent.futures import ThreadPoolExecutor

class Agent():
    def __init__(self, provider: LLMProvider, max_turns: int = 20):
        self.provider = provider # 直接傳入 provider = OllamaProvider(model_name)
        self.max_turns = max_turns
        self.history_messages = []

        self.executor = ThreadPoolExecutor(max_workers=4) # 任務池（同步處理工具調用）
        
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
                        "content": "[系統提示] 您已達到工具調用次數上限。請勿再調用工具，直接輸出最終回答，並總結當前進度與遇到的問題。"
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

            tools_result: List[Tuple] = [] # 存放 [{ToolCall 物件, 執行結果}, ...]

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

                    yield LLMResponse(status="prepare_tool")

                    for t in chunk.tool_calls:
                        # t 為 ToolCall 型別物件 

                        need_approval = getattr(TOOL_REGISTRY.get(t.tool_name, None), "need_approval", True)

                        if not need_approval or tool_approval(t.tool_name, t.args): # 不需審核或審核通過 -> 工具可調用

                            tools_result.append((t, self.executor.submit(execute_tool, t.tool_name, t.args)))

                        else: # 不可調用

                            tools_result.append((t, "[系統提示] 使用者基於安全考量拒絕了此工具的執行"))

            # ========== C. 多輪對話紀錄 ==========
            if tools_result: # 表示有 tool use 需求
                
                msg = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "name": t.tool_name,
                            "args": t.args,
                            "id": getattr(t, "id", None),
                            "thought_signature": getattr(t, "thought_signature", None)
                        } for t, _ in tools_result
                    ]
                }
                # 呼叫工具的訊息加入多輪
                if result_full_text.strip(): # 如果模型調用工具還有輸出文字
                    msg["content"] = result_full_text

                self.history_messages.append(msg)

                for t, tool_v in tools_result:

                    if hasattr(tool_v, "result"): # 檢查是否有 .result() 可用

                        result = tool_v.result()

                        is_sucess = True
                    else:
                        result = tool_v

                        is_sucess = False

                    self.history_messages.append(
                        {
                            "role": "tool",
                            "tool_name": t.tool_name,
                            "id": getattr(t, "id", None),
                            "content": result
                        }
                    )

                    status = "tool_executed" if is_sucess else "tool_rejected"
                    yield LLMResponse(status=status, tool_name=t.tool_name)
      
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