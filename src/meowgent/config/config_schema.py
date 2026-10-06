from pydantic import BaseModel, Field
from typing import Literal

class ModelsConfig(BaseModel):
    """ 模型相關 """

    default_model: str = Field(
        default="qwen3-vl:4b-thinking",
        description="模型"
    )

    temperature: float = Field(
        default=0.1,
        ge=0, le=1.5,
        description="溫度係數（0~1.5）"
    )

class SubagentConfig(BaseModel):
    """ 子模型相關 """

    sub_agent_model: str = Field(
        default="qwen3-vl:4b-thinking",
        description="子模型"
    )

    sub_temperature: float = Field(
        default=0.1,
        ge=0, le=1.5,
        description="溫度係數（0~1.5）"
    )

class AgentConfig(BaseModel):
    """ Agent 行為 """

    max_turns: int = Field(
        default=20,
        ge=1,
        description="每輪的最大工具調用次數"
    )

    tool_approval_mode: Literal["always ask", "default", "approval_all"] = Field(
        default="default",
        description="工具審核模式"
    )

class MeowgentConfig(BaseModel):

    models: ModelsConfig = Field(default_factory=ModelsConfig)

    sub_agent: SubagentConfig = Field(default_factory=SubagentConfig)

    agent: AgentConfig = Field(default_factory=AgentConfig)