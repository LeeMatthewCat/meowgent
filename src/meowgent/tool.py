from pathlib import Path 
import re
import subprocess
from typing import Annotated, Callable, Dict, Literal
import httpx
from readability import Document
import html2text
from mcp.server.mcpserver import MCPServer
import logging
from config.config_manager import CONFIG_DIR
from config import ConfigManager
import itertools

ROLE_PRESETS = {
    "explorer": {
        "rule": "你是一個專業的程式碼檢索專員。請在工作目錄中快速查找程式碼與檔案，並提供最簡明扼要的摘要結論。嚴禁修改任何檔案。",
        "tools": ["read_file", "list_file", "grep_search", "web_fetch"],  # 唯讀工具
    },
    "reviewer": {
        "rule": "你是一個嚴謹的代碼審查專員（Code Reviewer）。請仔細閱讀給定的程式碼檔案，指出架構設計問題、潛在 Bug 或可改進之處。",
        "tools": ["read_file"],  # 只需要讀檔
    },
    "tester": {
        "rule": "你是一個測試與除錯工程師。請執行測試指令，並分析回報的錯誤日誌與失敗原因。",
        "tools": ["read_file", "run_shell"],  # 允許執行終端命令
    },
}

_subagent_counter = itertools.count(1)
_subagent_callback = None

def set_subagent_callback(callback: Callable):
    """ 供外部（如 main.py）設定子 Agent 的狀態回呼函式 """
    global _subagent_callback
    _subagent_callback = callback

mcp = MCPServer("Meowgent")
logging.getLogger().handlers.clear() # 刪去 mcp 做的日誌綁定

TOOL_REGISTRY: Dict[str, Callable] = {}
def tool_register(need_approval: bool = True):
    """ 函數裝飾器：同時註冊到 MCP 伺服器與內部字典 """
    def decorator(func: Callable):
        func.need_approval = need_approval # 標記是否需要審批
        
        TOOL_REGISTRY[func.__name__] = func # 註冊給 agent.py 內部使用
        mcp.add_tool(func) # 註冊給 MCP 協議外部調用
        
        return func
    return decorator

def execute_tool(tool_name: str, args: dict) -> str:
    """ 供 agent.py 調用執行的統一入口 """
    if tool_name not in TOOL_REGISTRY:
        return f"錯誤：找不到工具 '{tool_name}'"
    try:
        tool_func = TOOL_REGISTRY[tool_name]
        return str(tool_func(**args))
    except Exception as e:
        return f"錯誤：執行工具 '{tool_name}' 失敗：{e}"

def _path_check(path: str) -> bool:

    cwd = Path.cwd().resolve() # 當前工作目錄
    path: Path = Path(path).expanduser().resolve()

    if path.is_relative_to(cwd):
        return True

    if path.is_relative_to(CONFIG_DIR.resolve()):
        return True

    return False

# ========== 工具 ==========
@tool_register(False)
def read_file(
    file_path: Annotated[str, "要讀取的檔案路徑（支援相對路徑或以 ~ 開頭的路徑）"]
) -> str:
    """ 讀取文字檔 """

    if not _path_check(file_path):
        return "路徑位於工作目錄之外，請更改路徑或向使用者提出更換工作目錄"

    try:
        return Path(file_path).expanduser().read_text(encoding="utf-8")
    except Exception as e:
        return f"錯誤：讀取檔案 '{file_path}' 失敗：{e}"

@tool_register(True)
def write_file(
    file_path: Annotated[str, "要寫入的目標檔案路徑"],
    content: Annotated[str, "要寫入檔案的完整文字內容"]
) -> str:
    """ 寫入到文字檔 """

    if not _path_check(file_path):
        return "路徑位於工作目錄之外，請更改路徑或向使用者提出更換工作目錄"

    try:
        Path(file_path).expanduser().parent.mkdir(parents=True, exist_ok=True) # 建立上層資料夾

        Path(file_path).expanduser().write_text(content, encoding="utf-8")

        return f"成功寫入檔案 '{file_path}'（共 {len(content.splitlines())} 行）"
        # content.splitlines() 字串分行拆成串列
    
    except Exception as e:
        return f"錯誤：寫入檔案 '{file_path}' 失敗：{e}"

@tool_register(True)
def edit_file(
    file_path: Annotated[str, "要修改的目標檔案路徑"],
    old_content: Annotated[str, "要被替換的原始文字片段（需與檔案內容完全相符且具唯一性）"],
    new_content: Annotated[str, "替換後的新文字內容"]
) -> str:
    """ 局部修改文字 """

    if not _path_check(file_path):
        return "路徑位於工作目錄之外，請更改路徑或向使用者提出更換工作目錄"

    try:
        # 擋掉空字串
        if not old_content:
            return "錯誤：old_content 不能為空字串。"

        p = Path(file_path).expanduser()

        if not p.is_file(): # 如果沒有此檔案
            return f"錯誤：找不到檔案 '{file_path}'"
        
        all_content = p.read_text(encoding="utf-8") # 讀檔案

        # 檢查內容是否存在
        if old_content not in all_content:
            return f"錯誤：在 '{file_path}' 中找不到指定的 '{old_content}'"
        
        # 檢查內容是否唯一
        occurrences = all_content.count(old_content)

        if occurrences > 1:
            return f"錯誤：在 '{file_path}' 中找到 {occurrences} 處相符的內容。old_content 必須具備唯一性才能安全取代。"

        # 寫入
        all_content = all_content.replace(old_content, new_content, 1)

        p.write_text(all_content, encoding="utf-8")

        return f"成功修改檔案 '{file_path}'"
    
    except Exception as e:
        return f"錯誤：修改檔案 '{file_path}' 時發生錯誤：{e}"

@tool_register(False)
def list_file(
    pattern: Annotated[str, "Glob 比對規則（例如 '*.*'、'**/*.py'、'src/*'）"], # Glob 規則
    base_path: Annotated[str, "搜尋起點目錄路徑（預設為 '.' 當前目錄）"] = ".", # 搜尋起點
    offset: Annotated[int, "起始筆數偏移量（預設為 0，用於分頁讀取長清單）"] = 0,
    limit: Annotated[int, "本次最多讀取的檔案數量（預設為 200）"] = 200
) -> str:
    """
    列出檔案
    如果要尋找專案外或使用者家目錄的檔案（例如 Downloads, Desktop），請務必修改 base_path 參數（如 '~/Downloads' 或 '/Users/...'）
    """

    files = []
    search_idx = 0 # 紀錄總共已經搜巡到多少個了（非保留多少個）
    has_more = False # 後面還有內容
    try:
        for file in Path(base_path).expanduser().glob(pattern):
            if not file.is_file():
                continue

            if search_idx >= offset: # 達到起始點索引

                if len(files) < limit:
                    files.append(str(file))
                else:
                    has_more = True
                    break # 告知後面還有內容，且退出迴圈（如果沒內容自己就結束迴圈了，不會到這）

            search_idx += 1
                
    except Exception as e:
        return f"錯誤：找不到路徑 '{base_path}'：{e}"

    return_files = "\n".join(files)

    if has_more:
        return_files += f"\n\n...[僅顯示第 {offset+1}~{offset + limit} 筆，若要看下一頁，請傳入 offset={offset + limit}]"
    return return_files

@tool_register(False)              
def grep_search(
    pattern: Annotated[str, "要搜尋的正則表達式或文字關鍵字（Regex Pattern），"], # Regex 表達式 -> 要比對的文字
    base_path: Annotated[str, "搜尋起點目錄路徑（預設為 '.' 當前目錄）"] = "." # 搜尋起點
) -> str:
    """ 搜尋文字檔內容 """

    if not _path_check(base_path):
        return "路徑位於工作目錄之外，請更改路徑或向使用者提出更換工作目錄"

    try:
        rx = re.compile(pattern) # 預先編譯，不用每次迴圈都編譯一次

    except re.error as e: # 捕捉正則編譯錯誤
        return f"錯誤：無效的正則表達式 '{pattern}'：{e}"

    try:

        match_contents = []
        for file in Path(base_path).expanduser().rglob("*"):

            if not file.is_file():
                continue # 非檔案，跳過

            try:
                content = file.read_text(encoding="utf-8")
            except Exception:
                continue # 非文字檔，跳過

            for line_num, line_content in enumerate(content.splitlines(), 1): # 切成行，計數從 1 開始
                if rx.search(line_content):
                    match_contents.append(f"{file}:{line_num}:{line_content.strip()}")

        return_matches = "\n".join(match_contents[:100]) # 只保留 100 個

        if len(match_contents) > 100:
            return_matches += "\n\n...（僅顯示前 100 筆比對結果。請使用更精確的搜尋 pattern 來縮小範圍）。"

        return return_matches
    except Exception as e:
        return f"錯誤：找不到路徑 '{base_path}'"

@tool_register(True) 
def run_shell(
    command: Annotated[str, "要在系統 Shell 執行的指令"]
) -> str:
    """ 執行終端指令 """

    try:
        execution = subprocess.run(
            command,
            shell=True, # 直接執行
            capture_output=True, # 回傳輸出或錯誤
            text=True, # 轉字串
            timeout=30, # 超過 30 秒則退出
            errors="replace" # 防止解碼報錯
        )

        if execution.returncode == 0: # 成功執行
            return execution.stdout if execution.stdout != "" else "（指令執行完成，無輸出內容）"
        else:
            return f"指令執行失敗（結束代碼 {execution.returncode}）：\n標準輸出 (Stdout)：{execution.stdout}\n標準錯誤 (Stderr)：{execution.stderr}"

    except subprocess.TimeoutExpired: # 攔截超時
        return f"錯誤：指令 '{command}' 執行超時（超過 30 秒）。"
    except Exception as e:
        return f"錯誤：執行指令時發生錯誤：{e}"

@tool_register(True)
def web_fetch(
    url: Annotated[str, "要抓取內容的網頁網址（必須以 http:// 或 https:// 開頭）"],
    offset: Annotated[int, "讀取內容的起始字元偏移量（預設為 0，用於分頁讀取長網頁）"] = 0,
    limit: Annotated[int, "本次讀取的最大字元數量（預設為 3000）"] = 3000
) -> str:
    """ 獲取網頁內容並轉成文字"""

    # ========== 1. 驗證爲網址與 HTTP 請求  ==========
    if not url.startswith(("http://", "https://")): # 非網址
        return "錯誤：這不是一個有效的網址（URL）"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    } # 偽裝為用戶，繞過反爬蟲

    try:
        response = httpx.get(
            url = url, # 網址
            headers=headers, # 請求的標頭字典
            follow_redirects=True, # 301 / 302 重定向轉址（防網址搬家）
            timeout=10 # 逾時限制
        )
        response.raise_for_status() # 拋出連線異常 httpx.HTTPStatusError

        text = response.content.decode(response.encoding or "utf-8", errors="ignore")

    except httpx.HTTPStatusError as e: # 攔截伺服器錯誤
        return f"錯誤：HTTP 狀態碼 {e.response.status_code} ({e.response.reason_phrase})"

    except httpx.RequestError as e: # 攔截網路連線錯誤
        return f"錯誤：網路連線失敗：{e}"

    # ========== 2. HTML -> Markdown ==========
    # ----- a. 提純 -----
    html_summary = Document(text).summary()

    if html_summary and len(html_summary) > 100: # 存在且沒有過度刪減
        text = html_summary
    # ----- b. 轉換 -----
    h = html2text.HTML2Text()

    h.ignore_images = True # 忽略圖片
    h.body_width = 0 # 不做自動換行
    h.single_line_break = True # 換行不隔行 -> 避免 .md 格式的兩行之間隔一行

    text = h.handle(text)

    # ========== 3. 定位切片點 ==========
    total_len = (len(text))

    if offset > total_len: # 起始點大於總文長
        return f"錯誤：指定的 offset ({offset}) 超出網頁內容總長度 ({total_len})"

    raw_end = offset + limit

    if raw_end >= total_len:
        end = total_len

    else: # 讓內容不斷在一半
        search_start = max(offset, raw_end - 500) # 往回推 500 為搜尋邊界

        target_idx = text.rfind("\n\n", search_start, raw_end) # 找最後出現的，故從右開始找

        end = target_idx if target_idx != -1 else raw_end

    # ========== 4. 切片及回傳 ==========
    suffix = f"\n\n[內容已截斷。若要閱讀下一頁，請呼叫 web_fetch 並帶入 offset={end}]" if total_len > end else ""

    return f"[顯示字元區間 {offset}~{end}，總字數為 {total_len}]\n" + text[offset:end] + suffix

@tool_register(True)
def subagent_once(
    task: Annotated[str, "要交付的任務說明"],
    role: Annotated[
        Literal["explorer", "reviewer", "tester"],
        "子 Agent 的角色：'explorer'（唯讀快速檢索代碼）、'reviewer'（審查代碼與抓 Bug）、'tester'（執行測試命令）"
    ]
):
    """
    將單次子任務委派給獨立的子 Agent 處理。
    子 Agent 會在背景自主查找資料並返回最終總結，執行完畢後立即關閉，不保留對話歷史。
    """
    from agent import Agent
    from providers import OllamaProvider 

    # ========== A. 初始化 ==========
    _, config = ConfigManager.load_config()

    sub_model_name = config.sub_agent.sub_agent_model

    rule = ROLE_PRESETS[role]["rule"]

    tool_list = ROLE_PRESETS[role]["tools"]

    sub_model = Agent(
        OllamaProvider(
            model_name=sub_model_name,
            temperature=config.sub_agent.sub_temperature,
        ),
        max_turns=config.agent.max_turns,
        tool_approval_mode="approval_all",
        tool_list=tool_list
    )

    sub_model.renew_system_prompt(
        rule=rule,
        model_name=sub_model_name,
        path=str(Path.cwd())
    )

    subagent_id = f"{role}#{next(_subagent_counter)}" # 子 agent id，用於辨識身份

    # ========== B. 調用模型 ==========
    final_report = ""

    for stream_content in sub_model.chat(
        user_input=task,
        tool_approval=lambda *args: True # 接收 t.tool_name、t.args，直接回傳 True
    ):
        if _subagent_callback:
            _subagent_callback(subagent_id, stream_content)

        if stream_content.status == "response":
            final_report = stream_content.content or ""

    # ========== C. 任務結束退場 ==========
    if _subagent_callback:
        _subagent_callback(subagent_id, is_end=True)

    return final_report if final_report.strip() else "（子 Agent 執行完畢，無輸出內容）"
