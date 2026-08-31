from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text
from rich.rule import Rule
from rich.padding import Padding
from rich.cells import cell_len
from typing import Callable

class ResponseStreamer: 
    def __init__(self, console: Console, render_func: Callable[[str], Group]):

        self.console = console
        self.render_func = render_func

        self.last_len = 0 # 上次更新的長度
        self.cache = ""

    def update_content(self, full_text: str, live: Live):

        update_len = len(full_text) - self.last_len # 需要被更新的字數
        self.last_len = len(full_text) # 更新目前字數

        self.cache += full_text[-update_len:] if update_len > 0 else ""

        in_code_block = (self.cache.count("```") % 2 != 0) # T -> 無成對程式碼，F -> 有

        if not in_code_block and "\n\n" in self.cache: # 沒有程式碼區塊，且有換行

            last_line_idx = self.cache.rfind("\n\n")

            live.update("") # 把上一次的 live 更新刪掉

            self.console.print(Padding(Markdown(self.cache[:last_line_idx]), (0, 0, 0, 2)))

            self.cache = self.cache[last_line_idx + 2:] 

        if self.cache.strip(): # 還有未完成的內容（下一行），包含有成對程式碼全在此更新
            
            live.update(self.render_func(self.cache))

    def reset(self, live: Live):
        """ 清空暫存並重置計數（工具調用時使用） """
        live.update("")
        self.cache = ""
        self.last_len = 0
        
    def clean(self, live:Live):
        """ 清除最後留在 live 的內容（轉為 console.print()）"""

        if self.cache.strip():

            live.update("")
            self.console.print(Padding(Markdown(self.cache), (0, 0, 0, 2)))
            self.console.print(Rule(style="dim", end=""))

        self.cache = ""
        self.last_len = 0

class CLIRenderer:
    def __init__(self):

        self.console = Console()

    def get_rule(self) -> Rule:
        return Rule(style="dim")

    def initialization(self):
        version = 1.0
        user_name = "matthew"

        self.console.print(f"[blue] Meowgent CLI {version}[/blue]\n[dim] {user_name}[/dim]\n")
        self.console.print(self.get_rule())

    def get_live(self, refresh_per_second: float = 10):
        """
        給定更新率，回傳 Live 版面
        """
        return Live(console=self.console, refresh_per_second=refresh_per_second, vertical_overflow="crop")

    def render_single_line_streamer(self, content: str):

        content = content.replace("\n", " ") # 換行替換為空格

        console_width = self.console.width - 2 # 扣除 2 的縮排

        if cell_len(content) > console_width: # 塞滿了做切片，因為中英佔的格數不同，不能值接切
            output = []
            occupy_width = 0
            for char in reversed(content): # 從最後面開始曲
                char_width = cell_len(char)

                if char_width + occupy_width > console_width:
                    break

                output.append(char)
                occupy_width += char_width

            content = "".join(reversed(output)) # 反轉回來拼成字串

        return Group(
            Padding(Markdown(content, style="dim"), (0 ,0, 0, 2)),
            self.get_rule()
        )

    def render_thinking_summary(self, think_time: float) -> Text: # 推理總結渲染
        return Padding(Text.from_markup(f"[dim]已思考{think_time}秒[/dim]"), (0 ,0, 0, 2))

    def render_tool_approval_result(self, tool_name: str, approval: bool) -> Text: # 工具調用結果渲染

        text_chunk = "[green]已被調用[/green]" if approval else "[red]未被調用[/red]"
        return Padding(Text.from_markup(f"[dim]{tool_name}[/dim] {text_chunk}"), (0 ,0, 0, 2))   

    def render_tool_calling_streamer(self, content: str) -> Group:
        """ 工具參數生成中的單行跑馬燈（復用思考跑馬燈的單行裁切排版邏輯） """
        return self.render_single_line_streamer(f"{content}")

    def render_model_response(self, content: str) -> Group: # 回答渲染
        return Group(
            Padding(Markdown(content), (1 ,0, 0, 2)),
            self.get_rule()
        )

    def get_response_streamer(self) -> ResponseStreamer:
        return ResponseStreamer(console=self.console, render_func=self.render_model_response)