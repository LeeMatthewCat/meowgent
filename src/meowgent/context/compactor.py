from .pruner import turn_separation
from typing import List
import re
import ollama
from config import ConfigManager

RX_STRIP_TOOL_RESPONSE = re.compile(
    r"<tool_response>\s*(?:\[工具\s*(\w+)\s*執行結果\]：)?\s*\n?([\s\S]*?)\s*</tool_response>"
)

COMPACTION_SYSTEM_PROMPT = """
你是一個程式碼開發助理的對話壓縮專家。
請將以下歷史對話紀錄提煉為一份結構化的「進度筆記」。
這份筆記將交給下一位接手的助理繼續工作，請嚴格按照以下四個標題輸出，不要包含任何無關客套話：

1. 【原始任務目標】：使用者最初要求解決的核心問題、任何特定限制或規則。
2. 【已知關鍵資訊】：已確認的專案架構、關鍵檔案路徑、函式位置。
3. 【已完成變更】：已經成功建立、修改的檔案，以及執行成功的終端指令。
4. 【目前狀態與下一步】：目前停在哪個步驟、遇到的錯誤或接下來準備執行的動作。

內容如下：
"""

def _format_history_msgs(history_messages: List[dict]) -> str:
    """
    將 history_messages 轉為扁平的文字格式（list -> str）
    1. 將使用者問題、工具結果、模型回答用文字區分
    2. 刪除工具調用結果的 XML 標籤
    """

    lines = []
    for msg in history_messages:

        role = msg["role"]
        content: str = msg["content"]

        if role == "user":

            if content.startswith("<tool_response>"):

                match = RX_STRIP_TOOL_RESPONSE.search(content)

                if match:
                    tool_name = match.group(1)
                    tool_content = match.group(2)

                else: # 正則沒找到 -> 簡單刪除標籤

                    tool_name = "工具輸出"
                    tool_content = content.replace("<tool_response>", "").replace("</tool_response>", "").strip()

                lines.append(f"[工具 {tool_name}]：\n{tool_content}")

            else:
                lines.append(f"[使用者]：{content}")

        elif role == "assistant":

            lines.append(f"[模型]：{content}")

    return "\n\n".join(lines)

def macro_compaction(
    history_messages: List[dict],
    keep_turns: int = 2
) -> List[dict]:
    """ 調用模型進行上下文壓縮 """

    turn_indices = turn_separation(history_messages)

    if len(turn_indices) <= keep_turns:
        return history_messages

    cutoff_idx = turn_indices[-keep_turns] # 邊界

    old_history_msgs = _format_history_msgs(history_messages[:cutoff_idx]) # 切出壓縮部分
    recently_history_msgs = history_messages[cutoff_idx:] # 切出保留部分

    prompt = f"{COMPACTION_SYSTEM_PROMPT}\n\n{old_history_msgs}"

    _, config = ConfigManager.load_config() # 取得設定檔

    compaction_content = ollama.generate(
        model=config.models.default_model,
        prompt=prompt,
        options={
            "num_ctx": config.models.max_context,
            "temperature": 0.1,
            "num_predict": 1024, # 限制輸出 token
            "repeat_penalty": 1.15 # 重複懲罰
        }
    ).response

    return [
        {
            "role": "user",
            "content": f"[系統提示：以下為前期歷史紀錄的壓縮筆記]\n{compaction_content}"
        },
        {
            "role": "assistant",
            "content": "已完整接收前期工作進度與任務目標，我將接續進行。"
        }
    ] + recently_history_msgs