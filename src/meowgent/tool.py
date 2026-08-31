from pathlib import Path 
import re
import subprocess
from typing import Annotated, Callable, Dict, Any
import httpx
from readability import Document
import html2text
from mcp.server.mcpserver import MCPServer
import logging

mcp = MCPServer("Meowgent")
logging.getLogger().handlers.clear() # 刪去 mcp 做的日誌綁定

TOOL_REGISTRY: Dict[str, Callable] = {}
def tool_register(need_approval: bool = True):
    """屬性裝飾器：同時註冊到 MCP 伺服器與內部字典"""
    def decorator(func: Callable):
        func.need_approval = need_approval # 標記是否需要審批
        
        TOOL_REGISTRY[func.__name__] = func # 註冊給 agent.py 內部使用
        mcp.add_tool(func) # 註冊給 MCP 協議外部調用
        
        return func
    return decorator

def execute_tool(tool_name: str, args: dict) -> str:
    """供 agent.py 調用執行的統一入口"""
    if tool_name not in TOOL_REGISTRY:
        return f"錯誤：找不到工具 '{tool_name}'"
    try:
        tool_func = TOOL_REGISTRY[tool_name]
        return str(tool_func(**args))
    except Exception as e:
        return f"錯誤：執行工具 '{tool_name}' 失敗：{e}"

# ========== 工具 ==========
@tool_register(False)
def read_file(
    file_path: Annotated[str, "要讀取的檔案路徑（支援相對路徑或以 ~ 開頭的路徑）"]
) -> str:
    """ 讀取文字檔 """
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
        return f"錯誤：找不到路徑 {base_path},{e}"

    return_files = "\n".join(files)

    if has_more:
        return_files += f"\n\n...[僅顯示第 {offset+1}~{offset + limit} 筆，若要看下一頁，請傳入 offset={offset + limit}]"
    return return_files

@tool_register(False)              
def grep_search(
    pattern: Annotated[str, "要搜尋的正則表達式或文字關鍵字（Regex Pattern）"], # Regex 表達式 -> 要比對的文字
    base_path: Annotated[str, "搜尋起點目錄路徑（預設為 '.' 當前目錄）"] = "." # 搜尋起點
) -> str:
    """ 搜尋文字檔內容 """
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
    command: Annotated[str, "要在系統終端機執行的 Shell 指令"]
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