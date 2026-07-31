from pathlib import Path 
import re
import subprocess

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
    # ----- 讀 -----
    try:
        all_content = Path(file_path).expanduser().read_text(encoding="utf-8")
    except Exception as e:
        return f"Error: can't reading file {file_path}: {e}"

    # ----- 檢查：1. 有舊內容 2. 舊內容不重複 -----
    if old_content not in all_content:
        return f"Error: cant't find {old_content} in {file_path}"
    else:
        if all_content.count(old_content) > 1:
            return f"Error: old_string found {all_content.count(old_content)} times in {file_path}. Must be unique to safely replace."
        else:
            # ----- 替換並寫入 -----
            all_content = all_content.replace(old_content, new_content)

            try:
                Path(file_path).expanduser().write_text(all_content, encoding="utf-8")
                return f"Successfully edited {file_path}"
            except Exception as e:
                return f"Error: can't writing(editing) file {file_path}: {e}"

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
            timeout=30 # 超過 30 秒則退出
        )

        if execution.returncode == 0: # 成功執行
            return execution.stdout if execution.stdout != "" else "(no output)"
        else:
            return f"Command failed (exit code {execution.returncode}):\nStdout: {execution.stdout}\nStderr: {execution.stderr}"
    except Exception as e:
        return f"Error: the command ({command} is execution too long time)"

def execute_tool(tool_name: str, tool_args: dict) -> str:
    """ 調用工具 """
    func = TOOL_REGISTRY.get(tool_name) # 找不到回傳 None

    if not func: # 找不到函數
        return f"Error: can't find {tool_name}"

    try:
        return func(**tool_args) # ** 拆包
    except Exception as e:
        return f"Error: executing tool {tool_name} with error"