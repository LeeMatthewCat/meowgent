from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, List, Any

@dataclass
class ToolCall:
    tool_name: str
    args: Dict[str, Any] # 要傳入工具函數的參數

@dataclass
class LLMResponse:
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


class LLMProvider(ABC):
    def __init__(
            self,
            model_provider: str,
            model_name: str
    ):
        self.model_provider = model_provider
        self.model_name = model_name
    
    @abstractmethod
    def generate(
        self,
        history_messages: list,
        tools: Optional[list] = None
    ) -> LLMResponse:
        """ 子類別強制實作，接收 prompt、工具，並回傳回答或調用工具 """
        pass
                 
        