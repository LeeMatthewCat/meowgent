from agent import Agent
from cli import CLIRenderer
import questionary
from questionary import Style
from rich.padding import Padding
import ollama
from typing import Callable
import sys

# ----- 函數註冊 -----
COMMAND_REGISTRY = {} # "指令": 對應函數
def cmd_registry(cmd_name: str, **kwargs): # 屬性裝飾器標註函數對應的指令

    def decorator(func: Callable):
        COMMAND_REGISTRY[cmd_name] = func

        return func
    return decorator
# -----

def handle_cmd(input: str,model_object: Agent, cli: CLIRenderer):

    func = COMMAND_REGISTRY.get(input.split()[0]) # 把空格以前切出來，也就是只切出指令部分，拿取函數物件，或回傳 None

    if not func: # 找不到
        cli.console.print(Padding("[red]查無此指令[/red]", (0, 0, 0, 2)))
    else: # 找到了
        func(
            args = input.split()[1:], # 把除了指令的內容傳入
            model_object=model_object,
            cli=cli
        ) # 將後面的參數傳入

@cmd_registry("/model")
def _change_model(model_object: Agent, cli: CLIRenderer, **kwargs):
    """ 選擇模型 """

    provider = questionary.select(
        "選擇模型供應商",
        choices=["ollama", "Gemini API", "取消"],
        style=Style([
            ('question', 'dim'),         
            ('instruction', 'dim')
        ])
    ).ask() # 先選擇模型供應商

    if provider == "取消":
        return None

    if provider == "ollama":
        try:
            new_model = questionary.select(
                "選擇模型",
                choices=[m.model for m in ollama.list()["models"]] + ["取消"],
                style=Style([
                    ('question', 'dim'),         
                    ('instruction', 'dim')
                ])
            ).ask() # 選擇模型

        except Exception: # ollama.list() 失敗時
            cli.console.print(Padding("[yellow]未偵測到本機已安裝的 Ollama 模型，或 Ollama 尚未啟動[/yellow]", (0, 0, 0, 2)))
            return None

        if new_model == "取消":
            return None

        model_object.provider.model_name = new_model
        model_object.renew_system_prompt(model_name=new_model)

        cli.console.print(Padding(f"[green]模型已成功切換為：{new_model}[/green]", (0, 0, 0, 2)))

    elif provider == "Gemini API":

        cli.console.print(Padding("[red]尚未完成，敬請期待[/red]", (0, 0, 0, 2)))

@cmd_registry("/exit")
def _exit(cli: CLIRenderer, **kwargs):
    """ 關閉 Meowgent """
    cli.console.print(Padding("[red]Meowgent 即將關閉[/red]", (0, 0, 0, 2)))

    sys.exit(0) # 退出程序

@cmd_registry("/cd")
def _change_path(arg: list, cli: CLIRenderer):
    "選擇工作目錄"

