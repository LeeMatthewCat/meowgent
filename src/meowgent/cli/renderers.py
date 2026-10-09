from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.rule import Rule
from rich.padding import Padding
from rich.cells import cell_len
from rich.spinner import Spinner
from rich.markup import escape

class ResponseStreamer: 
    def __init__(self, renderer: "CLIRenderer"):

        self.render = renderer
        self.console = self.render.console

        self.last_len = 0 # 上次更新的長度
        self.cache = ""

    def update_content(self, full_text: str, live: Live):

        update_len = len(full_text) - self.last_len # 需要被更新的字數
        self.last_len = len(full_text) # 更新目前字數

        self.cache += full_text[-update_len:] if update_len > 0 else ""

        done_code_block = (self.cache.count("```") % 2 == 0) # True -> 程式碼區塊完成

        last_tag_idx = self.cache.rfind("```")
        last_line_idx = self.cache.rfind("\n\n")

        if done_code_block and last_line_idx != -1 and last_line_idx > last_tag_idx:

            live.update("") # 把上一次的 live 更新刪掉

            self.console.print(Padding(Markdown(self.cache[:last_line_idx]), (0, 0, 1, 2)))

            self.cache = self.cache[last_line_idx + 2:] 

        if self.cache.strip(): # 還有未完成的內容（下一行），包含有成對程式碼全在此更新  
            live.update(
                Group(
                    Padding(Markdown(self.cache), (1, 0, 0, 2)),
                    self.render.get_rule()
                )
            )

    def reset(self, live: Live):
        """ 清空暫存並重置計數（工具調用時使用） """
        
        if self.cache.strip():
           live.update("")
           self.console.print(Padding(Markdown(self.cache), (0, 0, 0, 2))) 

        self.cache = ""
        self.last_len = 0
        
    def clean(self, live:Live):
        """ 清除最後留在 live 的內容（轉為 console.print()）"""

        if self.cache.strip():

            live.update("")
            self.console.print(
                Group(
                    Padding(Markdown(self.cache), (0, 0, 0, 2)),
                    self.render.get_rule()
                )
            )

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

    def get_live(self, refresh_per_second: float = 10) -> Live:
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
            Padding(Markdown(content, style="dim"), (0, 0, 0, 2)),
            self.get_rule()
        )

    def render_thinking_summary(self, think_time: float, subagent_name: str = "") -> Padding: # 推理總結渲染

        subagent_name = f"{escape(f'[{subagent_name}]')} " if subagent_name else ""
        
        return Padding(f"[dim]{subagent_name}已思考 {think_time} 秒[/dim]", (0, 0, 0, 2))

    def render_tool_approval_result(self, tool_name: str, approval: bool, subagent_name: str = "") -> Padding: # 工具調用結果渲染

        subagent_name = f" {escape(f'[{subagent_name}]')} " if subagent_name else ""

        text_chunk = f'[green]已被{subagent_name}調用[/green]' if approval else f"[red]未被{subagent_name}調用[/red]"
        
        return Padding(f"[dim]{tool_name}[/dim] {text_chunk}", (0, 0, 0, 2))

    def get_response_streamer(self) -> ResponseStreamer:
        return ResponseStreamer(renderer=self)

    def render_end(self, end_content: str = "") -> Padding:
        if end_content:
            end_content += "\n"

        return Padding(f"[red]{end_content}Meowgent 即將關閉[/red]", (0, 0, 0, 2))

    def render_not_support_vision(self) -> Padding:
        return Padding("[red]此模型不支援圖片[/red][dim]，若要讀取圖片請用 /model 切換至支援的模型[/dim]", (0, 0, 0, 2))
    
    def render_active_subagents(
        self,
        active_subagents: dict,
    ) -> Group:
        """ 將所有正在運作的子 agent 渲然轉圈圈動態 """
        if not active_subagents:
            return ""

        status_text_map = {
            "thinking": "思考分析中...",
            "tool_calling": "正在準備調用工具...",
            "response": "正在彙整分析結果...",
        }

        spinners = []
        for agent_id, st in active_subagents.items():
            text = status_text_map.get(st)
            
            # 產生轉圈圈物件
            spinners.append(
                Padding(
                    Spinner("dots", text=f"[dim]{escape(f'[{agent_id}]')} {text}[/dim]"),
                    (0, 0, 0, 2),
                )
            )

        # 底部加上一條分隔線
        return Group(*spinners, self.get_rule())

    def render_subagent_end(self, subagent_id: str) -> Padding:
        return Padding(f"[green]✔ {escape(f'[{subagent_id}]')} 任務已完成[/green]", (0, 0, 0, 2))