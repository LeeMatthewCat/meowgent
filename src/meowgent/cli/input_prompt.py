from prompt_toolkit import prompt, PromptSession
from prompt_toolkit.completion import WordCompleter
from typing import Optional
import questionary
from prompt_toolkit.styles import Style
from pathlib import Path
import inspect
from cli import COMMAND_REGISTRY

_prompt_session: Optional[PromptSession] = None # 內部私有

COMMANDS = [k for k in COMMAND_REGISTRY]

def get_input() -> str:

    global _prompt_session
    
    _prompt_session = PromptSession(
        style=Style.from_dict({
            "": "ansiblue"
        })
    ) if _prompt_session is None else _prompt_session # 歷史輸入管理，如果已經建立過，不再建立

    completer = WordCompleter(words=COMMANDS, ignore_case=True, WORD=True) # 建立補全器

    return _prompt_session.prompt("> ", completer=completer)

def get_tool_aproval(tool_name: str, tool_args: dict) -> bool:
    
    lines = []
    for k, v in tool_args.items():
        v_str = str(v)

        if "\n" in v_str:
            # 多行內容：每一行皆整齊縮排 4 格
            indented_v = "\n    ".join(v_str.splitlines())
            lines.append(f"  • {k}:\n    {indented_v}")
        else:
            lines.append(f"  • {k}: {v_str}")

    args = "\n".join(lines) if lines else "  (無參數)"

    return questionary.confirm(
        f"[工具調用]: {tool_name}\n{args}\n\n  是否允許執行？",
        default=True,
        style=Style([
            ("question", "dim"),         
            ("instruction", "dim")
        ])
    ).ask()

def select_directory(start_dir: Optional[str] = None) -> Optional[str]:

    if start_dir is None:
        now_dir = Path.home() # 若無傳入起點，則在主目錄
    else:
        now_dir = Path(start_dir)

    while True:
        file_list = ["選擇此目錄"]

        for item in now_dir.iterdir():

            if item.is_dir() and not item.name.startswith("."): # 是資料夾且分隱藏資料夾
                file_list.append(item.name)

        if now_dir != now_dir.parent: # 不在目錄最頂層 -> 加入上一頁
            file_list.append("上一頁")

        if Path(inspect.stack()[1].filename).name != "main.py": # 不在主程序呼叫（首次設定路徑）-> 可取消更改路徑
            file_list.append("取消")

        select_dir = questionary.select(
            "選擇工作目錄",
            file_list,
            style=Style([
                ("question", "dim"),         
                ("instruction", "dim")
            ])
        ).ask()

        if select_dir == "取消":
            break

        elif select_dir == "選擇此目錄":
            return str(now_dir) # Path -> str
        
        elif select_dir == "上一頁":
            now_dir = now_dir.parent

        else:
            now_dir = now_dir / select_dir