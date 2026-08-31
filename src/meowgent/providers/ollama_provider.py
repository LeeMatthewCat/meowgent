from .base import ToolCall, LLMProvider, StreamChunk
from typing import Optional, Iterator, List, Callable
import ollama
from tool import TOOL_REGISTRY
import json

class OllamaProvider(LLMProvider):
    def __init__(self, model_name: str):
        super().__init__(model_name=model_name)

    def stream_generate(self, history_messages: list) -> Iterator[StreamChunk]:

        # ========== A. 格式更改 ==========
        ollama_history_messsages = []
        for msg in history_messages: 
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
                            } for call in msg["tool_calls"] # 如果單次多個調用
                        ]
                    }
                )
            else: # 其餘不更改
                ollama_history_messsages.append(msg)

        # ========== B. 調用模型 ==========
        response = ollama.chat(
            model=self.model_name,
            messages=ollama_history_messsages,
            stream=True, # 流式輸出文字
            options={
                "num_ctx": 16384,
                "num_thread": 8, # 多執行緒，用幾個 GPU 核心
                "temperature": 0.1 # 降低隨機性
            }
        )
        # ========== C. 模型回傳處理 ==========
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

                content = chunk.message.content if chunk.message.content else None
                # 為空字串則 None

                yield StreamChunk(thinking_chunk=thinking, content_chunk=content) 