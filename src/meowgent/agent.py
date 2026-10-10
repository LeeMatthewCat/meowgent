import re
import json
from providers import LLMProvider, LLMResponse, ToolCall
from tool import execute_tool, TOOL_REGISTRY
from prompt import get_system_prompt
from typing import List, Callable, Optional, Iterator, Tuple
import time
from concurrent.futures import ThreadPoolExecutor

# ----- regex 預編譯 -----
RX_CODE_BLOCK = re.compile(r"^```json\s*|^```\s*|```$", flags=re.MULTILINE)
RX_GET_JSON = re.compile(r'"name"\s*:\s*"([^"]+)"')

RX_CJK_PATTERN = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]')
# -----

def _extract_safe_text(
    full_text: str,
    start_tag: str = "<tool_call>",
    end_tag: str = "</tool_call>"
) -> Tuple[str, Optional[str], List[str]]:
    """
    從流式累積文本中提取安全的人類可見文本、當前正在生成的工具參數文字（若有），
    以及已完整閉合的工具調用列表（raw 字串）。
    
    回傳:
        (safe_text, current_tool_text, completed_tools)
        - safe_text: 已確認安全的人類自然語言（已過濾工具標籤與未閉合前綴）
        - current_tool_text: 正在生成中的工具呼叫字串（若當前未在工具區間則為 None）
        - completed_tools: 已完整閉合（</tool_call> 之前）的工具 raw 內容列表
    """
    safe_parts = [] # 已經提取出的模型回覆
    completed_tools = [] # 已完整的工具調用請求
    current_tool_text = None # 尚未完整的工具調用請求
    start_pos = 0 # 目前進行到的索引
    full_len = len(full_text) # 目前全文長

    while start_pos < full_len: # 遍歷完全文
        start_target_idx = full_text.find(start_tag, start_pos)

        if start_target_idx == -1: # 後續沒有完整的 start_tag，檢查剩餘文字尾端是否有正在成形的前綴（如 "<tool"）

            remaining = full_text[start_pos:]
            trimmed_len = len(remaining) # 用於下方迴圈計數

            for i in range(len(start_tag) - 1, 0, -1):
                if remaining.endswith(start_tag[:i]):
                    trimmed_len -= i
                    break
            safe_parts.append(remaining[:trimmed_len])
            break
        else:
            # 收集 <tool_call> 之前的安全文字
            safe_parts.append(full_text[start_pos:start_target_idx])

            # 尋找對應的 </tool_call>
            content_start = start_target_idx + len(start_tag)
            end_idx = full_text.find(end_tag, content_start)

            if end_idx == -1:
                # 工具調用尚未閉合（正在輸出 JSON 中），後續文字為正在生成的工具文字
                current_tool_text = full_text[content_start:].strip()
                break
            else:
                # 找到完整的 </tool_call>，記錄已閉合工具，指針跳過整個工具區塊繼續向後掃描
                completed_tools.append(full_text[content_start:end_idx].strip())
                start_pos = end_idx + len(end_tag)

    return "".join(safe_parts), current_tool_text, completed_tools

def estimate_token(text: str) -> int:
    """ 估算出傳入文字的 token 量 """
    
    # 中日韓文、全形標點
    cjk_count = len(RX_CJK_PATTERN.findall(text))
    
    # 其餘字元（英文、數字、程式碼標點、半形空白等）
    other_chars_count = len(text) - cjk_count

    # 中文每字約 1.3 token，其餘每 3.5 字元約 1 token
    return int((cjk_count * 1.3) + (other_chars_count / 3.5))

class Agent():
    def __init__(self, provider: LLMProvider, max_turns: int = 20, tool_approval_mode: str = "default", tool_list: Optional[list] = None):
        self.provider = provider # 直接傳入 provider = OllamaProvider(model_name)
        self.max_turns = max_turns
        self.tool_approval_mode = tool_approval_mode
        self.tool_list = tool_list
        self.history_messages = []

        self.rule = None
        self.model_name = self.provider.model_name
        self.path = None

        self.executor = ThreadPoolExecutor(max_workers=4) # 任務池（同步處理工具調用

        self.true_token: Optional[int] = None
        self.last_system_prompt: Optional[str] = None # 記錄上次生效的提示詞

    def renew_system_prompt(self,rule: Optional[str] = None, model_name: Optional[str] = None, path: Optional[str] = None):
        """ 取得提示詞更新 """

        if rule is not None:
            self.rule = rule

        if model_name is not None:
            self.model_name = model_name
            self.provider.model_name = model_name

        if path is not None:
            self.path = path

    def get_context_status_text(self, user_input: Optional[str] = None) -> Optional[str]:
        """ 獲取上下文佔用文字 """

        system_prompt = get_system_prompt(
            model_name=self.model_name,
            path=self.path,
            rule=self.rule,
            enable_tools=True
        )
        
        # 最大上下文
        max_context = getattr(self.provider, "context", 16384) # 獲取 OllamaProvider 物件的 self.context
        max_context_k = round(max_context / 1000, 1)

        if self.true_token: 

            system_prompt_token_gap = 0
            if self.last_system_prompt and self.last_system_prompt != system_prompt:
                system_prompt_token_gap = estimate_token(system_prompt) - estimate_token(self.last_system_prompt) # 算出舊的跟新的差多少

            input_token = estimate_token(user_input) if user_input else 0

            total_token = self.true_token + system_prompt_token_gap + input_token

        else:
            
            total_text = system_prompt + (user_input or "")

            for msg in self.history_messages: # 取 sys prompt，讓沒 true_token 時也可正常運行
                total_text += msg["content"]

            total_token = estimate_token(total_text)

        total_token_k = round(total_token / 1000, 1) # 單位轉為 k

        percentage = round((total_token / max_context) * 100, 1)
        
        return f"[{total_token_k}k/{max_context_k}k] {percentage}%"
        
    def chat(self, user_input: str, tool_approval: Callable[[str, dict], bool], images: Optional[List[str]] = None) -> Iterator[LLMResponse]:
        
        user_msg = {
            "role": "user",
            "content": user_input
        }

        if images:
            user_msg["images"] = images

        self.history_messages.append(user_msg)

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
                        enable_tools=not is_last_turn, # 最後一輪禁用工具說明
                        tool_list=self.tool_list
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
            completed_tools: List[str] = [] # 存放已閉合的工具 raw 字串

            def thinking_finish() -> Optional[LLMResponse]:
                """ 判斷推理階段是否結束，若結束則計算並回傳推理耗時  """
                nonlocal is_thinking, think_start_time

                if is_thinking: # 表示為推理結束後進到回答或工具調用階段

                    think_time = round(time.perf_counter() - think_start_time, 1) # 更新計時

                    is_thinking = False

                    return LLMResponse(status="thinking_done", think_time=think_time)

                return None

            # ========== B. 處理模型回應 ==========
            for chunk in response:

                if chunk.token:
                    self.true_token = chunk.token

                    self.last_system_prompt = temp_history_messages[0]["content"] # 記下當前輪次的提示詞
            
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

                    # 分離
                    safe_text, tool_text, completed_tools = _extract_safe_text(result_full_text)

                    if tool_text is not None:
                        # 還未完成的工具調用參數
                        yield LLMResponse(status="tool_calling", content=tool_text)
                    elif safe_text:
                        # 模型回答
                        yield LLMResponse(status="response", content=safe_text)

            # ========== C. 標籤解析與多輪工具執行 ==========
            # 最後一輪時強制不執行工具（雙保險），確保輸出最終總結回答
            tools_to_execute = completed_tools if not is_last_turn else []

            if tools_to_execute:
                
                for raw_json in tools_to_execute:
                    try:
                        # 容錯清理 markdown 程式碼區塊符號（如 ```json ... ```）
                        cleaned_json = RX_CODE_BLOCK.sub("", raw_json,).strip()
                        call_data = json.loads(cleaned_json)

                        t = ToolCall(tool_name=call_data["name"], args=call_data.get("arguments", {}))

                        # ----- 審核模式判斷 -----
                        if self.tool_approval_mode == "approval_all":
                            need_approval = False

                        elif self.tool_approval_mode == "always ask":
                            need_approval = True

                        else: # "default" 時
                            need_approval = getattr(TOOL_REGISTRY.get(t.tool_name, None), "need_approval", True)
                        # -----

                        if not need_approval or tool_approval(t.tool_name, t.args):
                            tools_result.append((t, self.executor.submit(execute_tool, t.tool_name, t.args)))
                        else:
                            tools_result.append((t, "[系統提示] 使用者基於安全考量拒絕了此工具的執行"))

                    except Exception as e:
                        # 若 JSON 解析失敗，回饋錯誤提示
                        name_match = RX_GET_JSON.search(raw_json)
                        tool_name = name_match.group(1) if name_match else "unknown"

                        err_tool = ToolCall(tool_name=tool_name, args={})
                        tools_result.append((err_tool, f"[系統提示] 工具調用格式解析錯誤：{e}。請確保 <tool_call> 內嚴格為合法 JSON 格式。"))

            if tools_result: # 表示有 tool use 需求

                interrupted = False

                self.history_messages.append({
                    "role": "assistant",
                    "content": result_full_text
                })

                for t, tool_v in tools_result:
                    # t 為 ToolCall
                    # tool_v 為 Future 物件（執行中任務）或 str（被拒絕/出錯的提示字串）

                    if interrupted: # 前面工具已取消 -> 後面工具也取消
                        self.history_messages.append({
                            "role": "user",
                            "content": f"<tool_response>\n[工具 {t.tool_name} 執行結果]：\n[系統提示] 前序操作已被使用者手動中止，此工具已取消執行。\n</tool_response>"
                        })
                        continue
                    
                    try:
                        if hasattr(tool_v, "result"): # 檢查是否有 .result() 可用
                            result = tool_v.result()
                            is_success = True
                        else:
                            result = tool_v
                            is_success = False

                    except KeyboardInterrupt:

                        interrupted = True

                        result = "[系統提示] 工具執行已被使用者手動中止（KeyboardInterrupt）。"
                        
                        is_success = False

                    self.history_messages.append({
                        "role": "user",
                        "content": f"<tool_response>\n[工具 {t.tool_name} 執行結果]：\n{result}\n</tool_response>"
                    })

                    status = "tool_executed" if is_success else "tool_rejected"
                    yield LLMResponse(status=status, tool_name=t.tool_name)

                if interrupted:
                    self.history_messages.append({
                        "role": "assistant",
                        "content": "已停止執行後續操作。"
                    }) # 上一個訊息是 role 為 user 的 [系統提示] 工具執行已被使用者手動中止（KeyboardInterrupt）
                    # 防止接下來的使用者輸入跟它角色重疊

                    raise KeyboardInterrupt # 處理完了，重新拋出例外，否則會繼續下一個 while 迴圈
      
            else: # 沒有 tool use 需求，生成最終回答
                if not result_full_text.strip():
                    result_full_text = "（模型沒有回傳內容）"
                
                self.history_messages.append({
                    "role": "assistant",
                    "content": result_full_text
                })

                break # 模型沒有調用工具 -> 表示已經生成最終回答，故退出 while turns < self.max_turns: 迴圈