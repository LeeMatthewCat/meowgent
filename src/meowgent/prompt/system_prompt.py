from typing import Optional
import textwrap
import platform
from prompt import get_all_xml

def get_system_prompt(model_name: str, path: str, rule: Optional[str] = None, enable_tools: bool = True) -> str:

    if rule is None: # 預設角色規範
        rule = textwrap.dedent("""
            你是一名專業的程式碼編程助理。
            1. 協助使用者解決專案開發、檔案編輯與命令列操作。
            2. 必要時才調用工具，不過度使用工具，只有當任務明確需要檔案或指令操作時，才調用對應工具。
            3. 調用工具進行任何動作時，僅限在給定的工作目錄進行。
        """).strip()

    environment = textwrap.dedent(f""" 
        - 作業系統：{platform.system()}
        - 工作目錄：{path}
        - 目前模型：{model_name}
    """).strip() # 環境資訊
    
    tool_section = ""
    if enable_tools:
        mcp_tool = get_all_xml() # 可用工具

        tool_rule = textwrap.dedent(f"""
            當你需要使用工具時，必須嚴格使用 <tool_call> 標籤包裹 JSON，格式如下：
            <tool_call>
            {{"name": "工具名稱", "arguments": {{"參數名稱": "值"}}}}
            </tool_call>

            若需要同時執行多個無相依性的操作（例如同時讀取多個檔案或多個網頁），你可以在同一次回答中輸出多個 <tool_call>...</tool_call> 區塊，系統將會並發平行執行它們以提升效率。
        """).strip() # 工具調用格式

        tool_section = f"\n# 可用工具\n{mcp_tool}\n\n# 工具調用格式規範\n{tool_rule}"

    tool_section = tool_section if tool_section else "無可用工具"
    return textwrap.dedent(f"""
        # 角色與行為準則
        {rule}

        # 當前環境資訊
        {environment}

        # 工具調用
        {tool_section}
    """).strip()