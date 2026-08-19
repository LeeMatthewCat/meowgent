from pathlib import Path 
import re
import subprocess
import httpx
import html2text
from readability import Document

TOOL_REGISTRY = {} # 註冊表
def tool_register(need_approval: bool = True): # 屬性裝飾器
    def decorator(func):
        func.need_approval = need_approval # 是否需要許可才能被模型使用
        TOOL_REGISTRY[func.__name__] = func
        return func
    return decorator

# ========== 工具 ==========
@tool_register(False)
def read_file(file_path: str) -> str:
    """ 讀取文字檔 """
    try:
        return Path(file_path).expanduser().read_text(encoding="utf-8")
    except Exception as e:
        return f"Error: can't reading file {file_path}: {e}"

@tool_register(True)
def write_file(file_path: str, content: str) -> str:
    """ 寫入到文字檔 """
    try:
        Path(file_path).expanduser().parent.mkdir(parents=True, exist_ok=True) # 建立上層資料夾

        Path(file_path).expanduser().write_text(content, encoding="utf-8")

        return f"Successfully wrote to {file_path} ({len(content.splitlines())}) lines"
        # content.splitlines() 字串分行拆成串列
    
    except Exception as e:
        return f"Error: can't writing file {file_path}: {e}"

@tool_register(True)
def edit_file(file_path: str, old_content: str, new_content: str):
    """ 局部修改文字 """
    try:
        # 擋掉空字串
        if not old_content:
            return "Error: old_content cannot be empty."

        p = Path(file_path).expanduser()

        if not p.is_file(): # 如果沒有此檔案
            return f"Error: file not found at {file_path}"
        
        all_content = p.read_text(encoding="utf-8") # 讀檔案

        # 檢查內容是否存在
        if old_content not in all_content:
            return f"Error: can't find '{old_content}' in {file_path}"
        
        # 檢查內容是否唯一
        occurrences = all_content.count(old_content)

        if occurrences > 1:
            return f"Error: old_content found {occurrences} times in {file_path}. Must be unique to safely replace."

        # 寫入
        all_content = all_content.replace(old_content, new_content, 1)

        p.write_text(all_content, encoding="utf-8")

        return f"Successfully edited {file_path}"
    
    except Exception as e:
        return f"Error editing file {file_path}: {e}"

@tool_register(False)
def list_file(
    pattern: str, # Glob 規則
    base_path: str = "." # 搜尋起點
) -> str:
    """
    列出檔案
    如果要尋找專案外或使用者家目錄的檔案（例如 Downloads, Desktop），請務必修改 base_path 參數（如 '~/Downloads' 或 '/Users/...'）
    """
    files = []
    try:
        for file in Path(base_path).expanduser().glob(pattern):
            if file.is_file():
                files.append(str(file))
    except Exception as e:
        return f"Error: can't find the path {base_path}"

    return_files = "\n".join(files[:200]) # 只保留 200 個

    if len(files) > 200:
        return_files += f"\n\n... (Showing top 200 of {len(files)} files. Please use a more specific pattern to narrow down)."
    return return_files

@tool_register(False)              
def grep_search(
    pattern: str, # Regex 表達式 -> 要比對的文字
    base_path: str = "." # 搜尋起點
) -> str:
    """ 搜尋文字檔內容 """
    try:
        rx = re.compile(pattern) # 預先編譯，不用每次迴圈都編譯一次

    except re.error as e: # 捕捉正則編譯錯誤
        return f"Error: Invalid regular expression '{pattern}': {e}"

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
            return_matches += "\n\n... (Showing top 100 matches. Please use a more specific search pattern to narrow down)."

        return return_matches
    except Exception as e:
        return f"Error: can't find the path {base_path}"

@tool_register(True) 
def run_shell(command: str) -> str:
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
            return execution.stdout if execution.stdout != "" else "(no output)"
        else:
            return f"Command failed (exit code {execution.returncode}):\nStdout: {execution.stdout}\nStderr: {execution.stderr}"

    except subprocess.TimeoutExpired: # 攔截超時
        return f"Error: The command '{command}' timed out (exceeded 30 seconds)."
    except Exception as e:
        return f"Error executing command: {e}"

def execute_tool(tool_name: str, tool_args: dict) -> str:
    """ 調用工具 """
    func = TOOL_REGISTRY.get(tool_name) # 找不到回傳 None

    if not func: # 找不到函數
        return f"Error: can't find {tool_name}"

    try:
        return func(**tool_args) # ** 拆包
    except Exception as e:
        return f"Error: executing tool {tool_name} with error, {e}"

@tool_register(True)
def web_fetch(url: str, offset: int = 0, limit: int = 3000) -> str:
    """ 獲取網頁內容並轉成文字"""

    # ========== 1. 驗證爲網址與 HTTP 請求  ==========
    if not url.startswith(("http://", "https://")): # 非網址
        return f"Error: this is not a url"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    } # 偽裝為用戶，繞過反爬蟲

    try:
        response = httpx.get(
            url = url,
            headers=headers,
            follow_redirects=True,
            timeout=10
        )
        response.raise_for_status() # 拋出連線異常 httpx.HTTPStatusError

        text = response.content.decode(response.encoding or "utf-8", errors="ignore")

    except httpx.HTTPStatusError as e: # 攔截伺服器錯誤
        return f"Error: HTTP status {e.response.status_code}({e.response.reason_phrase})"

    except httpx.RequestError as e: # 攔截網路連線錯誤
        return f"Error: Connection/Network failed: {e}"

    # ========== 2. HTML -> Markdown ==========
    # ----- a. 提純 -----
    doc = Document(text)

    html_summary = doc.summary()

    if html_summary and len(html_summary) > 100: # 存在且沒有過度刪減
        text = html_summary
    # ----- b. 轉換 -----
    h = html2text.HTML2Text()
    h.ignore_images = True # 忽略圖片
    h.body_width = 0 # 不做自動換行
    h.single_line_break = True # 換行不隔行

    text = h.handle(text)

    # ========== 3. 定位切片點 ==========
    total_len = (len(text))

    if offset > total_len: # 起始點大於總文長
        return f"Error: designated offest ({offset}) is longer than the web content ({total_len})"

    raw_end = offset + limit

    if raw_end >= total_len:
        end = total_len
    else:
        search_start = max(offset, raw_end - 500) # 往回推 500 為搜尋邊界

        target_idx = text.rfind("\n\n", search_start, raw_end) # 找最後出現的，故從右開始找

        end = target_idx if target_idx != -1 else raw_end

    # ========== 4. 切片及回傳 ==========
    suffix = f"[The content has been truncated. To read the next page, call web_fetch with offset={end}]" if total_len > end else ""

    return f"[show the words {offset}~{end}, total words is{total_len}]" + text[offset:end] + suffix