from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text
from rich.rule import Rule
from rich.padding import Padding

class CLIRenderer:
    def __init__(self, model_provider: str, model: str, main_color:str =  "blue"):
        self.model_provider = model_provider
        self.model = model
        self.main_color = main_color

        self.console = Console()

    def get_rule(self) -> Rule:
        return Rule(style="dim")

    def initialization(self):
        version = 1.0
        user_name = "matthew"

        self.console.print(f"[blue] MeowCode CLI {version}[/blue]\n[dim] {user_name}[/dim]\n")
        self.console.print(self.get_rule())

    def get_live(self, refresh_per_second: float = 10):
        """
        給定更新率，回傳 Live 版面
        """
        return Live(console=self.console, refresh_per_second=refresh_per_second, vertical_overflow="visible")

    def render_thinking_content(self, content: str) -> Group: # 推理內容渲染
        return Group(
            Padding(Markdown(content, style="dim"), (0 ,0, 0, 2)),
            self.get_rule()
        )

    def render_thinking_summary(self, think_time: float) -> Text: # 推理總結渲染
        return Padding(Text.from_markup(f"[dim]已思考{think_time}秒[/dim]"), (0 ,0, 0, 2))

    def render_model_response(self, content: str) -> Group: # 回答渲染
        return Group(
            Padding(Markdown(content), (1 ,0, 0, 2)),
            self.get_rule()
        )
    def render_tool_approval_result(self, tool_name: str, approval: bool) -> Text: # 工具調用結果渲染

        text_chunk = "[green]已被調用[/green]" if approval else "[red]未被調用[/red]"
        return Padding(Text.from_markup(f"[dim]{tool_name}[/dim] {text_chunk}"), (0 ,0, 0, 2))