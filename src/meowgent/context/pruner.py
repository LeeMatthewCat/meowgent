from typing import List, Tuple
import re

RX_TOOL_RESPONSE = re.compile(
    r"<tool_response>\s*\[工具\s*(\w+)\s*執行結果\]：\n([\s\S]*?)\n</tool_response>"
)

def _turn_separation(history_messages: List[dict]) -> List[int]:
    """ 得到為使用者輸入的索引 """

    turn_indices = []

    for idx, msg in enumerate(history_messages):
        if msg["role"] == "user":
            
            # 排除工具執行的回傳標籤
            if not msg["content"].startswith("<tool_response>"):
                turn_indices.append(idx)

    return turn_indices

def pruner_tool_text(history_messages: List[dict], keep_turns: int = 2):
    """
    """

    turn_indices = _turn_separation(history_messages)

    if len(turn_indices) <= keep_turns: # 還不需要裁剪
        return history_messages

    cutoff_idx = turn_indices[-keep_turns] # 界定要裁切分界點
    # 在 cutoff_idx -1 之前都要檢查

    for idx in range(cutoff_idx):

        msg = history_messages[idx]
        content = msg["content"]

        if msg["role"] == "user" and content.startswith("<tool_response>"):

            if "... [省略前期工具" in content:
                continue

            match = RX_TOOL_RESPONSE.search(content)
            if not match:
                continue

            tool_name = match.group(1)
            raw_result = match.group(2) # 工具輸出的字串

            # 檢查行數 -> 超過，留前三後二
            lines = raw_result.splitlines()
            if len(lines) > 6:

                head = "\n".join(lines[:3]) # 保留索引 0~2
                tail = "\n".join(lines[-2:]) # 倒數第二個開始留

                result = (
                    f"{head}\n"
                    f"... [省略前期工具 {tool_name} 的部分輸出]\n"
                    f"{tail}"
                )
            elif len(raw_result) > 300:

                head = raw_result[:50]
                tail = raw_result[-50:]

                result = head + f" ... [省略前期工具 {tool_name} 的部分輸出] " + tail

            else:
                continue

            msg["content"] = f"<tool_response>\n[工具 {tool_name} 執行結果]：\n{result}\n</tool_response>"

    return history_messages