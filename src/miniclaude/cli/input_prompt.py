from prompt_toolkit import prompt, PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from typing import Optional, List
import questionary
from questionary import Style
from prompt_toolkit.styles import Style as PTStyle

def get_input(complete_words: Optional[List[str]] = None, color:str = "ansiblue") -> str:
    """
    獲取用戶輸入，需傳入補全字庫及顏色
    """
    completer = WordCompleter(words=complete_words, ignore_case=True) if complete_words is not None else None # 建立補全器

    session = PromptSession(
        style=PTStyle.from_dict({
            '': 'ansiblue'
        })
    ) # 輸入歷史紀錄管理的初始化

    return session.prompt(HTML(f"<{color}>> </{color}>"), completer=completer)

def get_tool_aproval(tool_name: str) -> bool:
    return questionary.confirm(
        f"是否允許調用{tool_name}",
        default=False,
        style=Style([
            ('question', 'dim'),         
            ('instruction', 'dim')
        ])
    ).ask()