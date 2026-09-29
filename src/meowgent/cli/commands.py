from __future__ import annotations
from cli import CLIRenderer
import questionary
from questionary import Style
from rich.padding import Padding
import ollama
from typing import Callable
import sys
from pathlib import Path
import os
from config import MeowgentConfig, ConfigManager
import inspect
from rich.panel import Panel
from pydantic import BaseModel, ValidationError
from typing import get_origin, get_args, Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent import Agent

# ----- 函數註冊 -----
COMMAND_REGISTRY = {} # "指令": 對應函數
def cmd_registry(cmd_name: str, **kwargs): # 屬性裝飾器標註函數對應的指令

    def decorator(func: Callable):
        COMMAND_REGISTRY[cmd_name] = func

        return func
    return decorator
# -----

def handle_cmd(input: str, model_object: Agent, cli: CLIRenderer, config: MeowgentConfig):

    func = COMMAND_REGISTRY.get(input.split()[0]) # 把空格以前切出來，也就是只切出指令部分，拿取函數物件，或回傳 None

    if not func: # 找不到
        cli.console.print(Padding("[red]查無此指令[/red]", (0, 0, 0, 2)))
    else: # 找到了
        func(
            args = input.split()[1:], # 把除了指令的內容傳入
            model_object=model_object,
            cli=cli,
            config=config
        ) # 將後面的參數傳入

@cmd_registry("/model")
def _change_model(model_object: Agent, cli: CLIRenderer, config: MeowgentConfig, **kwargs):
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

        # ----- 存檔 -----
        config.models.default_model = new_model
        ConfigManager.save_config(config)
        # -----  

        cli.console.print(Padding(f"[green]模型已成功切換為：{new_model}[/green]", (0, 0, 0, 2)))

    elif provider == "Gemini API":

        cli.console.print(Padding("[red]尚未完成，敬請期待[/red]", (0, 0, 0, 2)))

@cmd_registry("/exit")
def _exit(cli: CLIRenderer, **kwargs):
    """ 關閉 Meowgent """
    cli.console.print(cli.render_end())

    sys.exit(0) # 退出程序

@cmd_registry("/cd")
def _change_path(args: list, cli: CLIRenderer, model_object: Agent, **kwargs):
    """ 選擇工作目錄 """
    from cli import select_directory
    if args:

        path = Path(" ".join(args)).expanduser()

        if path.is_dir():
            new_path = path

        else:
            cli.console.print(Padding("[red]查無此路徑[/red]", (0, 0, 0, 2)))
            
            new_path = select_directory(start_dir=str(Path.cwd()))
            
    else:
        new_path = select_directory(start_dir=str(Path.cwd()))

    if new_path:
        os.chdir(new_path)

        model_object.renew_system_prompt(path=str(Path.cwd()))

        cli.console.print(Padding(f"[dim]路徑已切換到 {str(Path.cwd())}[/dim]", (0, 0, 0, 2)))

@cmd_registry("/help")
def _show_commands(cli: CLIRenderer, **kwargs):
    """ 顯示各指令以及詳細功能 """

    lines = []
    for cmd_name, cmd_func in COMMAND_REGISTRY.items():
        doc = inspect.getdoc(cmd_func).strip()

        lines.append(f"[blue]{cmd_name: <15}[/blue][dim]{doc}[/dim]")

    cli.console.print(Panel.fit(
        "\n".join(lines),
        title="可用指令",
        border_style="dim",
        padding=(0, 1, 0, 1)
    ))
    cli.console.print(cli.get_rule())

@cmd_registry("/config")
def _change_config(cli: CLIRenderer, config: MeowgentConfig, model_object: Agent, **kwargs):
    """ 更改設定項目 """

    def _cancel_select():
        cli.console.print(Padding("[red]退出設定更改[/red]", (0, 0, 0, 2)))
        cli.console.print(cli.get_rule())

    def _type_validator(input: str) -> Optional[str]:
        """ 驗證輸入使否合規 """

        nonlocal new_value # 宣告修改外層變數（閉包）

        format_dict = sub_mdoel.model_dump() # 取出內容轉字典

        format_dict[field_name] = input # 將輸入值替換進去
        
        try:
            validated_obj = sub_class.model_validate(format_dict)

            new_value = getattr(validated_obj, field_name) # 已經不是字串，而是正確型別了

            return True
        
        except ValidationError as e:
            return f"驗證錯誤 {e.errors()[0]["msg"]}"
        
        except Exception as e:
            return f"錯誤 {e}"
        
    # ========== 初始化 ==========
    choices = [questionary.Separator("|")]
    
    cat_item = list(MeowgentConfig.model_fields.keys())
    cat_num = len(cat_item)

    # ========== A. 先拿上層大類別 ==========
    for cat_idx, cat_name in enumerate(cat_item):
        # cat -> category 類別

        sub_mdoel = getattr(config, cat_name) # getattr(...) 相當於 config.model、config.agent
        sub_class: type[BaseModel] = sub_mdoel.__class__ # 取得類別

        cat_doc = inspect.getdoc(sub_class).strip() # 名字（模型相關、Agent 行為）

        tree_prefix = "└──" if cat_idx == cat_num - 1 else "├──"
        choices.append(questionary.Separator(f"{tree_prefix} {cat_doc}"))

        # ========== B. 獲取大類別裡的每個子項目 ==========
        field_item = list(sub_class.model_fields.items())
        field_num = len(field_item)

        for idx, (field_name, field_info) in enumerate(field_item):
            
            # 項目當前值
            now_value = getattr(sub_mdoel, field_name) # 相當於 config.model.default_model
            
            # 項目解釋
            desc = field_info.description # Field() 裡的 description 參數

            indent = "    " if cat_idx == cat_num - 1 else "│   "
            branch = "└── " if idx == field_num - 1 else "├── "

            choices.append(questionary.Choice(
                title=f"{indent + branch}{desc} (目前: {now_value})",
                value=(cat_name, field_name)
            ))

        if cat_idx < cat_num - 1:
            choices.append(questionary.Separator("│"))

    # ========== C. 選單收尾 ==========
    choices.append(questionary.Separator()) # 分隔線
    choices.append("離開設定")

    # ========== D. 開始選擇 ==========
    select = questionary.select(
        message="選擇設定項目",
        choices=choices
    ).ask()

    # ========== E. 解析選擇 ==========

    # ----- a. 退出 -----
    if select == "離開設定" or select == None:
        _cancel_select()
        return
    
    # ----- b. 模型選單 -----
    if select == ("models", "default_model"):
        _change_model(model_object=model_object, cli=cli, config=config)
        return

    # ----- c. 提取資訊及發送選項 -----
    cat_name, field_name = select # 提取出選擇

    sub_mdoel: BaseModel = getattr(config, cat_name)
    sub_class = sub_mdoel.__class__

    field_info = sub_class.model_fields[field_name] # 取出欄位內的內容
    now_value = getattr(sub_mdoel, field_name) # 當前值
    desc = field_info.description
    value_type = field_info.annotation

    new_value = None

    # -- 1. Literal 的 -- 
    if get_origin(value_type) is Literal:

        options = list(get_args(value_type))
        options.append("取消")

        new_value = questionary.select(
            message=f"請選擇 {desc}：",
            choices=options
        ).ask()

        if new_value == "取消" or new_value == None:
            _cancel_select()
            return
    
    # -- 2. 一般型別 --
    else:
        text_result = questionary.text(
            message=f"輸入 {desc} 的值：",
            default=str(now_value), # 要求為字串，要避免為數字
            validate=_type_validator # 會驗證直到通過（True），或 ctrl-c or esc 取消（None）
        ).ask()

        if text_result is None: # 如果輸入完值並完成驗證但最後退出選擇（因為驗證是邊輸入就邊在跑的）
            _cancel_select()
            return

    # ========== F. 存檔 ==========
    if new_value is not None and new_value != now_value: # 成功更改值

        setattr(sub_mdoel, field_name, new_value) # 更改屬性

        ConfigManager.save_config(config)

        if cat_name == "models" and field_name == "temperature":
            if hasattr(model_object.provider, "temperature"):
                model_object.provider.temperature = new_value
        elif cat_name == "agent":
            if field_name == "max_turns":
                model_object.max_turns = new_value
            elif field_name == "tool_approval_mode":
                model_object.tool_approval_mode = new_value

        cli.console.print(Padding(f"[green]{desc} 由 {now_value} 更新至 {new_value}[/green]", (0, 0, 0, 2)))

    else:
        cli.console.print(Padding(f"[dim]設定未變更[/dim]", (0, 0, 0, 2)))