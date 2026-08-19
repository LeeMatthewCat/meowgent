from .base import ToolCall, LLMProvider, StreamChunk
from typing import Optional, Iterator, List, Callable
import ollama
from tool import TOOL_REGISTRY
import json

class OllamaProvider(LLMProvider):
    def __init__(self, model_name: str):
        super().__init__(model_name=model_name)

    def stream_generate(self, history_messages: list, tools:Optional[List[Callable]] = None) -> Iterator[StreamChunk]:

        # ========== A. 工具函數註冊表轉串列 ==========
        tools_list = tools if tools is not None else list(TOOL_REGISTRY.values())
        # 可傳入指定函數物件（在串列裡）則只使用它

        # ========== B. 格式更改 ==========
        ollama_history_messsages = []
        for msg  in history_messages: 
            # msg 為 dict
            if msg["role"] == "assistant" and "tool_calls" in msg: # 對模型提出的工具調用做格式處理
                ollama_history_messsages.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content") or "",
                        "tool_calls": [
                            {
                                "function":{
                                    "name": call["name"],
                                    "arguments": call["args"]
                                }
                            } for call in msg["tool_calls"]
                        ]
                    }
                )
            else: # 其餘不更改
                ollama_history_messsages.append(msg)

        # ========== C. 調用模型 ==========
        response = ollama.chat(
            model=self.model_name,
            messages=ollama_history_messsages,
            stream=True, # 流式輸出文字
            tools=tools_list,
            options={"num_ctx": 16384}
        )
        # ========== D. 模型回傳處理 ==========
        # 一次回傳一個 token 的內容，通過 agent.py 不斷呼叫達成流式輸出
        for chunk in response:
            if chunk.message.tool_calls: # tool use 時

                tool_calls = []
                for t in chunk.message.tool_calls:

                    raw_args = t.function.arguments

                    if isinstance(raw_args, str): # 防止模型傳入的參數為 JSON 格式（用字串傳入）
                        try:
                            parsed_args = json.loads(raw_args) # "{}" -> {}
                        except:
                            parsed_args = {"raw_input": raw_args}
                    else:
                        parsed_args = dict(raw_args) if raw_args else {}

                    tool_calls.append(ToolCall(tool_name=t.function.name, args=parsed_args)) # 回傳函數以及對應的參數

                yield StreamChunk(tool_calls=tool_calls)

            else: # 推理或回答時

                thinking = getattr(chunk.message, "thinking", None) # 用 getattr 防止模型沒有推理功能（沒有 message.thinking 屬性）
                # 有推理能力模型在非推理時 message.thinking 回傳 None

                content = chunk.message.content

                yield StreamChunk(thinking_chunk=thinking, content_chunk=content)   