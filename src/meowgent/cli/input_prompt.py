from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from typing import Optional, List, Tuple, Callable
import questionary
from prompt_toolkit.styles import Style
from pathlib import Path
import inspect
from cli import COMMAND_REGISTRY
import re
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from questionary.prompts.common import InquirerControl
import subprocess
from rich.padding import Padding
from rich.console import Console
from prompt_toolkit.application.run_in_terminal import in_terminal

_prompt_session: Optional[PromptSession] = None # 內部私有

COMMANDS = [k for k in COMMAND_REGISTRY]

RX_IMAGE_PATH = re.compile(
    r"""(?:[~/\.]|\b[a-zA-Z]:[/\\])(?:\\ |[^\s])+\.(?:png|jpg|jpeg|webp|bmp)""",
    flags=re.IGNORECASE # 忽略大小寫差異
) # 正則預編譯

attached_images: List[str] = [] # 圖片路徑暫存

is_updating_input = False # T -> 修改是程式碼替換路徑為空白造成的，不是使用者打新的字，不要觸發 _on_text_change()

just_extracted = False # 剛提取出圖片路徑，終端自動加上了空格並再觸發 _on_text_change()，要把這個空格去掉

class CommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # 只有在整行「以 / 開頭」且「還沒有按空格」時才跳出指令補全
        if text.startswith("/") and " " not in text:
            for cmd in COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))

def get_input(rprompt: Optional[Callable] = None) -> Tuple[str, List[str]]:

    def _get_image_toolbar_text():
        """ 獲得加入照片的文字提示 """
        if not attached_images:
            return None

        text = "，".join([f"{Path(p).name}" for p in attached_images])

        return f"已附加圖片：{text}"

    def _on_text_change(buffer: Buffer):
        """ 清理輸入顯示圖片路徑 """
        global is_updating_input, just_extracted

        if is_updating_input: # 擋住循環
            return

        clean_text = _extract_image_path(buffer.text)

        if just_extracted:
            just_extracted = False
            clean_text = clean_text.rstrip()

        if clean_text != buffer.text: # 防止內容一樣（白改了）

            is_updating_input = True # 開始修改了，不要再觸發自己
            
            just_extracted = True # 不要觸發空格
            
            try:
                buffer.text = clean_text

            finally:
                is_updating_input = False
    
    def _dynamic_rprompt():
        """ 回呼函數，用來實時取得上下文佔用文字 """
        
        if not rprompt:
            return ""
        
        return rprompt(_prompt_session.default_buffer.text)
        # 取得當前輸入（buffer 內）傳入 rprompt() 回傳

    global _prompt_session
    
    if _prompt_session is None:

        kb = KeyBindings()
        
        @kb.add("c-o", eager=True) # 捕捉 ctrl o
        async def catch_del_img(event):
            async with in_terminal():
                await _del_image()
            event.app.invalidate()

        _prompt_session = PromptSession(
            style=Style.from_dict({
                "": "ansiblue",
                "rprompt": "#888888"
            }),
            completer=CommandCompleter(),
            bottom_toolbar=_get_image_toolbar_text,
            key_bindings=kb
        ) # 歷史輸入管理，如果已經建立過，不再建立

        _prompt_session.default_buffer.on_text_changed += _on_text_change # 掛載清理函數

    user_input =  _prompt_session.prompt("> ", rprompt=_dynamic_rprompt).strip()
    
    # ----- 使用者輸入已結束 -----

    images = list(attached_images) # 淺拷貝複製
    attached_images.clear()

    if not user_input and images: # 只有圖片，沒文字
        user_input = "根據上下文內容處理圖片"

    return user_input, images

def get_tool_approval(tool_name: str, tool_args: dict) -> bool:
    
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

def _extract_image_path(input: str) -> str:
    """
    過濾文字中是否有圖片
    """

    matches: List[str] = RX_IMAGE_PATH.findall(input)

    if not matches: # 無任何匹配
        return input

    for row_path in matches:

        path = Path(row_path.replace(r"\ ", " ")).expanduser().resolve() # 替換跳脫字元

        if path.is_file():

            input = input.replace(row_path, "") # 把路徑在文字中刪除
            
            if str(path) not in attached_images:

                attached_images.append(str(path)) # 加入暫存

    return input.strip()

async def _del_image():
    """ 刪除加到對話中的圖片 """
    from cli import attached_images

    console = Console()

    def _render_del_msg():
        console.print(Padding(f"[red]{Path(del_img).name} 已移除[/red]", (0, 0, 0, 2)))

    if not attached_images:
        console.print(Padding("[dim]無圖片[/dim]", (0, 0, 0, 2)))
        return

    elif len(attached_images) == 1: # 如果只有一張 -> 直接刪
        del_img = attached_images[0]
        attached_images.clear()
        _render_del_msg()
        return

    else:
        repeat = False
        while attached_images: # 刪光時離開

            img_list = []
            for img in attached_images:
                img_list.append(questionary.Choice(title=Path(img).name, value=img))

            q = questionary.select(
                "選擇要刪除的圖片",
                choices=img_list + (["不繼續選擇"] if repeat else ["取消"]),
                instruction="(Enter: 刪除, Ctrl+O: 開啟圖片)",
                style=Style([
                    ("question", "dim"),         
                    ("instruction", "dim")
                ])
            )
            repeat = True

            ic = next(c for c in q.application.layout.find_all_controls() if isinstance(c, InquirerControl))

            @q.application.key_bindings.add("c-o", eager=True)
            def _open_preview(event):

                current_img = ic.get_pointed_at().value

                if current_img not in ("不繼續選擇", "取消"):  
                    subprocess.Popen(["open", current_img])

            del_img = await q.ask_async()

            if del_img in ("不繼續選擇", "取消", None):
                return

            attached_images.remove(del_img)
            _render_del_msg()