from abc import abstractmethod

from .base import ToolCall, LLMProvider, StreamChunk
from typing import Optional, Iterator, List, Callable
from google import genai
from google.genai import types
from tool import TOOL_REGISTRY

class GeminiProvider(LLMProvider):
    def __init__(self, model_name: str):
        super().__init__(model_name=model_name)

        self.client = genai.Client() # 初始化模型

    def stream_generate(self, history_messages: list, tools: Optional[List[Callable]] = None) -> Iterator[StreamChunk]:

        # ========== A. 格式修改 ==========
        gemini_history_messages = []
        for msg in history_messages:
            
                if msg["role"] == "user": # 使用者輸入
                    gemini_history_messages.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(text=msg["content"])
                            ]
                        )
                    )

                elif "tool_calls" in msg: # 模型調用工具
                    parts = []
                    for t in msg["tool_calls"]:
                        fc = types.FunctionCall(name=t["name"], args=t["args"]) # 實作 FunctionCall

                        if t.get("id"):
                            fc.id = t["id"]
                        part = types.Part(function_call=fc) # FunctionCall 組裝回 Part

                        if t.get("thought_signature"):
                            part.thought_signature = t["thought_signature"] # 在 Part 貼上 thought_signature 標籤
                        parts.append(part) # 組裝好的 Part 放回串列

                    gemini_history_messages.append(
                        types.Content(
                            role="model",
                            parts=parts
                        )
                    )

                elif "tool_name" in msg: # 傳回工具執行結果
                    
                    fr = types.FunctionResponse(
                        name=msg["tool_name"],
                        response={"result": msg["content"]}
                    )
                    if msg.get("id"):
                        fr.id = msg["id"] 
                        
                    new_part = types.Part(function_response=fr)
                    
                    if gemini_history_messages[-1].role == "user":
                        gemini_history_messages[-1].parts.append(new_part) # 若前一個也為 user 合併進去
                    else:
                        # 不然照正常方式，新增一個
                        gemini_history_messages.append(
                            types.Content(role="user", parts=[new_part])
                        )

                else: # 模型回答
                    gemini_history_messages.append(
                        types.Content(
                            role="model",
                            parts=[
                                types.Part.from_text(text=msg["content"])
                            ]
                        )
                    )

        # ========== B. 工具函數註冊表轉串列 ==========
        tools_list = tools if tools is not None else list(TOOL_REGISTRY.values())
        # 可傳入指定函數物件（在串列裡）則只使用它
        
        # ========== C. 遞交給模型 ==========
        response = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=gemini_history_messages,
            config=types.GenerateContentConfig(
                tools=tools_list,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            ),  
        )

        # ========== D. 解析調用函數 ==========
        for chunk in response:
            
            if not chunk.parts: # 防止模型出現拒絕回答（資安問題）、生成錯誤等情況
                continue

            if chunk.function_calls:
                tool_calls = []
                for part in chunk.parts:

                    if part.function_call:

                        tool_calls.append(
                            ToolCall(
                                tool_name=part.function_call.name,
                                args=part.function_call.args,
                                id=getattr(part.function_call, "id", None),
                                thought_signature=getattr(part, "thought_signature", None)
                            )
                        )

                yield StreamChunk(tool_calls=tool_calls)
                
            else: # 推理或回答時
                for part in chunk.parts:
                    if getattr(part, "thought", False):
                        yield StreamChunk(thinking_chunk=part.text)
                    else:
                        yield StreamChunk(content_chunk=part.text)
                    # 若為推理情況返回推理文字，反之正式回答文字（兩者共用 part.text 屬性）