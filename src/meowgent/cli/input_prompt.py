from prompt_toolkit import prompt, PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from typing import Optional, List
import questionary
from questionary import Style
from prompt_toolkit.styles import Style as PTStyle

_prompt_session: Optional[PromptSession] = None # 內部私有

def get_input(complete_words: Optional[List[str]] = None) -> str:
    """
    獲取用戶輸入，需傳入補全字庫及顏色
    """
    global _prompt_session
    
    _prompt_session = PromptSession(
        style=PTStyle.from_dict({
            '': 'ansiblue'
        })
    ) if _prompt_session is None else _prompt_session # 歷史輸入管理，如果已經建立過，不再建立

    completer = WordCompleter(words=complete_words, ignore_case=True) if complete_words is not None else None # 建立補全器

    return _prompt_session.prompt(HTML(f"<ansiblue>> </ansiblue>"), completer=completer)

def get_tool_aproval(tool_name: str, tool_args: dict) -> bool:

    lines = [f"  •{k}: {v}" for k, v in tool_args.items()]
    args = "\n".join(lines) if lines else "(無參數)"

    msg = f"[工具調用]:{tool_name}\n{args}\n  是否允許執行？"

    return questionary.confirm(
        msg,
        default=True,
        style=Style([
            ('question', 'dim'),         
            ('instruction', 'dim')
        ])
    ).ask()