from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, List, Any, Iterator, Literal

@dataclass
class ToolCall:
    tool_name: str
    args: Dict[str, Any] # 要傳入工具函數的參數

    # 針對 gemini api
    id: Optional[str] = None # 工具調用編號
    thought_signature: Optional[Any] = None # 推理簽名（用於調用完工具後找回先前的推理邏輯）

@dataclass
class LLMResponse:
    status: Literal["response", "thinking", "thinking_done", "prepare_tool", "tool_executed", "tool_rejected"]
    content: Optional[str] = None
    think_time: Optional[float] = None
    tool_name: Optional[str] = None
    
@dataclass
class StreamChunk:
    """ 統一串流（流式輸出）協定 """
    thinking_chunk: Optional[str] = None
    content_chunk: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None

class LLMProvider(ABC):
    def __init__(
            self,
            model_name: str
    ):
        self.model_name = model_name
    
    @abstractmethod
    def stream_generate(
        self,
        history_messages: list,
        tools: Optional[list] = None
    ) -> Iterator[StreamChunk]:
        pass
        