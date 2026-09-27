from .config_schema import MeowgentConfig
from pathlib import Path
import shutil
from .config_manager import CONFIG_FILE, ConfigManager
from cli import CLIRenderer
import textwrap
import questionary
from prompt_toolkit.styles import Style
from rich.padding import Padding

def repair(config: MeowgentConfig, cli: CLIRenderer) -> MeowgentConfig:
    from agent import Agent
    from providers import OllamaProvider
    from cli import get_tool_approval

    # ========== A. 讀取壞檔與備份 ==========
    backup_path = shutil.copy2(CONFIG_FILE, CONFIG_FILE.with_suffix(".json.bak")) # 備份

    # ========== B. 呼叫模型做修復 ==========
    model = Agent(
        OllamaProvider(model_name=config.models.default_model, temperature=config.models.temperature),
        max_turns=config.agent.max_turns,
        tool_approval_mode=config.agent.tool_approval_mode
    )

    while True:
        prompt = textwrap.dedent(f"""
            你是一個專門修復損壞 JSON 設定檔的助理，且回答時力求精簡。
            以下是這份設定檔應當符合的正確 JSON Schema 規範：
            {MeowgentConfig.model_json_schema()}

            對無法正常解析的 JSON 內容做修復：
            ```json
            {CONFIG_FILE.read_text(encoding="utf-8")}
            ```

            在不更動原始數據的前提下，用 write_file 工具，
            直接將 {CONFIG_FILE} 修改成正確樣式，
            盡量在只使用一次工具的情況下準確完成。
            
            調用工具前不說客套話、開場白，例如「好的，我調用工具來做修復：」，直接調用工具。
        """)
    
        executed_tool = False
        for chunk in model.chat(
            user_input=prompt,
            tool_approval=get_tool_approval
        ):
            if chunk.status == "tool_executed":
                executed_tool = True
            
            elif chunk.status == "response" and executed_tool:
                break

        # ========== C. 驗證格式正確性 ==========
        success, config = ConfigManager.load_config()

        if success:
            break
        else:
            if questionary.confirm(
                "格式驗證失敗，是否交由模型繼續修復",
                default=False,
                style=Style([
                    ("question", "dim"),         
                    ("instruction", "dim")
                ])
            ).ask() is False:
                break

    # ========== D. 存檔 ==========
    cover_confirm = False
    use_default_confirm = False
    if success: # 如果驗證格式格式
        cli.console.print(Padding("[green]模型成功修復設定檔[/green]", (0, 0, 0, 2)))
        cover_confirm = questionary.confirm(
            "已成功修復設定檔，是否覆蓋套用？",
            default=True,
            style=Style([
                ("question", "dim"),         
                ("instruction", "dim")
            ])
        ).ask()

    if cover_confirm: # 使用者同意套用模型的修復
    
            ConfigManager.save_config(config)
    
            cli.console.print(Padding("[green]修復檔成功覆蓋[/green]", (0, 0, 0, 2)))
            return config

    if not success or not cover_confirm:
        # 如果模型修復的還是沒辦法讀 or 使用者拒絕用模型修復的

        remind = "已取消使用模型修復的檔案" if success else "模型修復失敗"

        use_default_confirm = questionary.confirm(
            f"{remind}，是否將預設設定覆蓋到設定檔（已將損壞檔案備份於 {backup_path}）",
            default=True,
            style=Style([
                ("question", "dim"),         
                ("instruction", "dim")
            ])
        ).ask() 
    
    elif use_default_confirm: # 使用者同意套用預設值 -> 重置為全新乾淨的預設物件！

        config = MeowgentConfig()
        ConfigManager.save_config(config)

        cli.console.print(Padding("[green]已套用預設設定[/green]", (0, 0, 0, 2)))

        return config
    
    else: # 使用者不同意套用預設 -> 還原原始備份，當次以預設物件開機

        shutil.copy2(backup_path, CONFIG_FILE)

        cli.console.print(Padding("[green]備份檔已恢復[/green]", (0, 0, 0, 2)))

        return MeowgentConfig()