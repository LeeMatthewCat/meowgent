import inspect
import textwrap
from typing import Callable, get_args
from pydantic import TypeAdapter
from tool import TOOL_REGISTRY

_MCP_TOOL_CACHE = ""

def _tool_to_mcp_xml(tool: Callable) -> str:
    """將單個 Python 工具函式轉換為緊湊的 XML 節點格式"""
    sig = inspect.signature(tool)
    params_xml = []

    for arg_name, arg in sig.parameters.items():
        # ========== A. 提取型別與說明 ==========
        args_list = get_args(arg.annotation)
        type = TypeAdapter(args_list[0]).json_schema()["type"]
        desc = args_list[1]
        
        # ========== B. 必填／選填判定 ==========
        is_required = (arg.default == inspect.Parameter.empty)
        required_str = " (必填)" if is_required else " (選填)"
        required_attr = "true" if is_required else "false"

        # ========== C. 轉成單行 XML 參數描述 ==========
        params_xml.append(f'            <parameter name="{arg_name}" type="{type}" required="{required_attr}">')
        params_xml.append(f'              <description>{desc}{required_str}</description>')
        params_xml.append(f'            </parameter>')

    # ========== D. 組裝 ==========
    params_block = "\n".join(params_xml)
    doc = inspect.getdoc(tool) or ""
    
    return textwrap.dedent(f"""
        <tool name="{tool.__name__}">
          <description>{doc.strip()}</description>
          <parameters>
            {params_block.lstrip()}
          </parameters>
        </tool>
    """).strip()

def get_all_xml() -> str:
    """取得所有已註冊工具的完整 XML 區塊（帶快取）"""
    global _MCP_TOOL_CACHE
    
    if not _MCP_TOOL_CACHE:
        tool_nodes = []
        for _, tool in TOOL_REGISTRY.items():
            tool_nodes.append(_tool_to_mcp_xml(tool))
        
        # 組裝成完整的 <tools> XML 區塊
        _MCP_TOOL_CACHE = "<tools>\n" + "\n".join(tool_nodes) + "\n</tools>"
        
    return _MCP_TOOL_CACHE