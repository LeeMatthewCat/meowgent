import re
import json
from providers import LLMProvider, LLMResponse, ToolCall
from tool import execute_tool, TOOL_REGISTRY
from prompt import get_system_prompt
from typing import List, Callable, Optional, Iterator, Tuple
import time
from concurrent.futures import ThreadPoolExecutor

def _extract_safe_text(
    full_text: str,
    start_tag: str = "<tool_call>",
    end_tag: str = "</tool_call>"
) -> Tuple[str, Optional[str]]:
    """
    從流式累積文本中提取安全的人類可見文本，以及當前正在生成的工具參數文字（若有）。
    
    回傳:
        (safe_text, current_tool_text)
        - safe_text: 已確認安全的人類自然語言
        - current_tool_text: 正在生成中的工具呼叫字串（若當前未在工具區間則為 None）
    """
    safe_parts = []
    current_tool_text = None
    pos = 0
    full_len = len(full_text)

    while pos < full_len:
        start_idx = full_text.find(start_tag, pos)

        if start_idx == -1:
            # 後續沒有完整的 start_tag，檢查剩餘文字尾端是否有正在成形的前綴（如 "<tool"）
            remaining = full_text[pos:]
            trimmed_len = len(remaining)
            for i in range(len(start_tag) - 1, 0, -1):
                if remaining.endswith(start_tag[:i]):
                    trimmed_len -= i
                    break
            safe_parts.append(remaining[:trimmed_len])
            break
        else:
            # 收集 <tool_call> 之前的安全文字
            safe_parts.append(full_text[pos:start_idx])

            # 尋找對應的 </tool_call>
            content_start = start_idx + len(start_tag)
            end_idx = full_text.find(end_tag, content_start)

            if end_idx == -1:
                # 工具調用尚未閉合（正在輸出 JSON 中），後續文字為正在生成的工具文字
                current_tool_text = full_text[content_start:].strip()
                break
            else:
                # 找到完整的 </tool_call>，指針跳過整個工具區塊，繼續向後掃描
                pos = end_idx + len(end_tag)

    return "".join(safe_parts), current_tool_text

class Agent():
    def __init__(self, provider: LLMProvider, max_turns: int = 20):
        self.provider = provider # 直接傳入 provider = OllamaProvider(model_name)
        self.max_turns = max_turns
        self.history_messages = []

        self.rule = None
        self.model_name = self.provider.model_name
        self.path = None

        self.executor = ThreadPoolExecutor(max_workers=4) # 任務池（同步處理工具調用）

    def renew_system_prompt(self,rule: Optional[str] = None, model_name: Optional[str] = None, path: Optional[str] = None):
        """ 取得提示詞更新 """

        if rule is not None:
            self.rule = rule

        if model_name is not None:
            self.model_name = model_name
            self.provider.model_name = model_name

        if path is not None:
            self.path = path
        
        
    def chat(self, user_input: str, tool_approval: Callable[[str, dict], bool]) -> Iterator[LLMResponse]:
        
        self.history_messages.append(
            {
                "role": "user",
                "content": user_input
            }
        ) # 使用者輸入加入多輪

        turns = 0
        while turns < self.max_turns: # 模型內迴圈，使用者輸入，模型多次調用
            # turns 為 self.max_turns - 1 時表示為最後一次
            
            # ========== A. 初始化、請求模型 ==========

            turns += 1 # 計數 +1
            is_last_turn = (turns == self.max_turns) # 是否為最後一輪

            # ----- 加入 system prompt（最後一輪不給工具，從物理上杜絕模型調用） -----
            temp_history_messages = [
                {
                    "role": "system",
                    "content": get_system_prompt(
                        model_name=self.model_name,
                        path=self.path,
                        rule=self.rule,
                        enable_tools=not is_last_turn # 最後一輪禁用工具說明
                    )
                }
            ] + self.history_messages

            # ----- 對於達到上限的處理（不動到 self.history_messages）-----
            if is_last_turn:
                temp_history_messages.append(
                    {
                        "role": "user",
                        "content": "[系統提示] 您已達到工具調用次數上限。請勿再調用工具，直接輸出最終回答，並總結當前進度與遇到的問題。"
                    }
                )
            # -----

            response = self.provider.stream_generate(
                history_messages=temp_history_messages
            ) # 請求模型
            
            thinking_full_text = ""
            result_full_text = ""

            is_thinking = False
            think_start_time = None

            tools_result: List[Tuple] = [] # 存放 [{ToolCall 物件, 執行結果}, ...]

            def thinking_finish() -> Optional[LLMResponse]:
                """ 判斷推理階段是否結束，若結束則清除版面並顯示推理時間 """
                nonlocal is_thinking, think_start_time

                if is_thinking: # 表示為推理結束後進到回答或工具調用階段

                    think_time = round(time.perf_counter() - think_start_time, 1) # 更新計時

                    is_thinking = False

                    return LLMResponse(status="thinking_done", think_time=think_time)

                return None

            # ========== B. 處理模型回應 ==========
            for chunk in response:
            
                if chunk.thinking_chunk: # 推理
                    is_thinking = True
                    think_start_time = time.perf_counter() if think_start_time is None else think_start_time # 如果沒開始計時（此次推理第一個 token 出現時）開始計時

                    # 流式輸出
                    thinking_full_text += chunk.thinking_chunk
                    yield LLMResponse(status="thinking", content=thinking_full_text)

                if chunk.content_chunk: # 回答及工具調用輸出
                    thinking_status = thinking_finish()
                    if thinking_status:
                        yield thinking_status

                    result_full_text += chunk.content_chunk

                    # 抽出工具調用與人類文字
                    safe_text, tool_text = _extract_safe_text(result_full_text)

                    if tool_text is not None:
                        # 正在生成工具參數：輸出單行跑馬燈事件
                        yield LLMResponse(status="tool_calling", content=tool_text)
                    elif safe_text:
                        # 流式輸出人類回答
                        yield LLMResponse(status="response", content=safe_text)

            # ========== C. 標籤解析與多輪工具執行 ==========
            # 最後一輪時強制不解析工具（雙保險），確保輸出最終總結回答
            tool_matches = list(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", result_full_text, re.DOTALL)) if not is_last_turn else []

            if tool_matches:
                for match in tool_matches:
                    raw_json = match.group(1).strip() # 為 str
                    try:
                        # 容錯清理 markdown 程式碼區塊符號（如 ```json ... ```）
                        cleaned_json = re.sub(r"^```json\s*|^```\s*|```$", "", raw_json, flags=re.MULTILINE).strip()
                        call_data = json.loads(cleaned_json)

                        t = ToolCall(tool_name=call_data["name"], args=call_data.get("arguments", {}))

                        need_approval = getattr(TOOL_REGISTRY.get(t.tool_name, None), "need_approval", True)

                        if not need_approval or tool_approval(t.tool_name, t.args):
                            tools_result.append((t, self.executor.submit(execute_tool, t.tool_name, t.args)))
                        else:
                            tools_result.append((t, "[系統提示] 使用者基於安全考量拒絕了此工具的執行"))

                    except Exception as e:
                        # 若 JSON 解析失敗，回饋錯誤提示
                        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', raw_json)
                        tool_name = name_match.group(1) if name_match else "unknown"

                        err_tool = ToolCall(tool_name=tool_name, args={})
                        tools_result.append((err_tool, f"[系統提示] 工具調用格式解析錯誤：{e}。請確保 <tool_call> 內嚴格為合法 JSON 格式。"))

            if tools_result: # 表示有 tool use 需求
                self.history_messages.append({
                    "role": "assistant",
                    "content": result_full_text
                })

                for t, tool_v in tools_result:
                    # t 為 ToolCall，tool_v
                    # tool_v 為 Future 物件（執行中任務）或 str（被拒絕/出錯的提示字串）
                    
                    if hasattr(tool_v, "result"): # 檢查是否有 .result() 可用
                        result = tool_v.result()
                        is_sucess = True
                    else:
                        result = tool_v
                        is_sucess = False

                    self.history_messages.append({
                        "role": "user",
                        "content": f"<tool_response>\n[工具 {t.tool_name} 執行結果]：\n{result}\n</tool_response>"
                    })

                    status = "tool_executed" if is_sucess else "tool_rejected"
                    yield LLMResponse(status=status, tool_name=t.tool_name)
      
            else: # 沒有 tool use 需求，生成最終回答
                if not result_full_text.strip():
                    result_full_text = "（模型沒有回傳內容）"
                
                self.history_messages.append({
                    "role": "assistant",
                    "content": result_full_text
                })

                break # 模型沒有調用工具 -> 表示已經生成最終回答，故退出 while turns < self.max_turns: 迴圈