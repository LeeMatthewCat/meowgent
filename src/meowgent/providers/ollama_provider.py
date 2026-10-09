from .base import LLMProvider, StreamChunk
from typing import Iterator
import ollama

class OllamaProvider(LLMProvider):
    def __init__(self, model_name: str, temperature: float = 0.1, context: int = 16384):
        super().__init__(model_name=model_name)
        self.temperature = temperature
        self.context = context

    def stream_generate(self, history_messages: list) -> Iterator[StreamChunk]:

        # ========== A. 調用模型 ==========
        response = ollama.chat(
            model=self.model_name,
            messages=history_messages,
            stream=True, # 流式輸出文字
            options={
                "num_ctx": self.context,
                "num_thread": 8, # 多執行緒，用幾個 GPU 核心
                "temperature": self.temperature # 降低隨機性
            }
        )
        # ========== B. 模型回傳處理 ==========
        # 一次回傳一個 token 的內容，通過 agent.py 不斷呼叫達成流式輸出
        for chunk in response:

            thinking = getattr(chunk.message, "thinking", None) # 用 getattr 防止模型沒有推理功能（沒有 message.thinking 屬性）
            # 有推理能力模型在非推理時 message.thinking 回傳 None

            content = chunk.message.content if chunk.message.content else None
            # 為空字串則 None

            # ----- token 回傳 -----
            token = None
            if chunk.done: # 輸出完成時

                prompt_eval = getattr(chunk, "prompt_eval_count", 0) or 0
                eval_cnt = getattr(chunk, "eval_count", 0) or 0

                if prompt_eval or eval_cnt:
                    token = prompt_eval + eval_cnt # 輸入的 token（含歷史）+ 輸出的 token
            # -----

            yield StreamChunk(thinking_chunk=thinking, content_chunk=content, token=token) 