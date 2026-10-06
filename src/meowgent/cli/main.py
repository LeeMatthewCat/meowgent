from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from providers import LLMResponse

from agent import Agent
from providers import OllamaProvider
from dotenv import load_dotenv
from cli import get_input, get_tool_approval, CLIRenderer, start_ollama, clean_ollama, handle_cmd, select_directory
import os
import sys
from config import ConfigManager, repair
import ollama
import threading
from typing import Optional
from tool import set_subagent_callback

load_dotenv() # 讀取 .env

_subagents_active_status = {}
_subagent_lock = threading.Lock() # 防止多個執行緒同時修改 _active_subagents

def on_subagent_status(subagent_id: str, stream_content: Optional[LLMResponse] = None, is_end: bool = False):
    """
    子模型的回調參數，
    針對 subagent_once() 傳入的狀態做輸出
    """ 

    with _subagent_lock:

        if is_end:
            _subagents_active_status.pop(subagent_id, None) # 刪除

            cli.console.print(cli.render_subagent_end(subagent_id))

            live.update(cli.render_active_subagents(_subagents_active_status))

            return

        if stream_content is None:
            return

        status = stream_content.status

        last_status = _subagents_active_status.get(subagent_id)

        # 動態
        if status in ("thinking", "tool_calling", "response"):

            if status != last_status: # 狀態改變才刷新

                _subagents_active_status[subagent_id] = status

                live.update(cli.render_active_subagents(
                    active_subagents=_subagents_active_status,
                ))
        # 靜態
        elif status == "thinking_done":
            cli.console.print(cli.render_thinking_summary(stream_content.think_time))

        elif status == "tool_executed":
            cli.console.print(cli.render_tool_approval_result(stream_content.tool_name, True, subagent_id))

        elif status == "tool_rejected":
            cli.console.print(cli.render_tool_approval_result(stream_content.tool_name, False, subagent_id))


if __name__ == "__main__":

    cli = CLIRenderer() 
    set_subagent_callback(on_subagent_status)
    
    cli.initialization() # 初始介面

    # ----- ollama 開啟 -----
    success, process = start_ollama() # 啟動 ollama 進程
    
    if not success:
        cli.console.print(cli.render_end("ollama 未被正常啟動"))

        sys.exit(1) # 異常退出
    # -----

    # ----- 設定檔載入 -----
    config_success, config = ConfigManager.load_config()

    if not config_success: # 未成功
        config = repair(config=config, cli=cli)
    # -----

    # ----- 初始化模型 ----
    model_name = config.models.default_model
    model = Agent(
        OllamaProvider(model_name=model_name, temperature=config.models.temperature),
        max_turns=config.agent.max_turns,
        tool_approval_mode=config.agent.tool_approval_mode
    )

    path = select_directory()
    model.renew_system_prompt(
        rule=None, # 採用預設規則
        model_name=model_name,
        path=path
    )
    # -----

    os.chdir(path) # 進入指定工作目錄

    def ask_tool_approval(tool_name: str, tool_args: dict) -> bool:

        live.update("") # 清除分隔線，否則調用許可會出現在分隔線下方
        live.stop() # 停止 live 更新

        try:
            approval = get_tool_approval(tool_name, tool_args) # 呼叫取得輸入

        finally:

            live.start() # 重啟 live 更新

        return approval

    try:

        while True: # 對話迴圈

            user_input, images = get_input()

            if not user_input and not images: # 擋住空字串傳入
                continue

            if images:
                if "vision" not in (ollama.show(model.model_name).capabilities or []): # 不支援視覺時
                    images = None

                    cli.console.print(cli.render_not_support_vision())

                    user_input = "[系統提示：使用者原本附帶了圖片，但當前模型不支援視覺讀取，圖片已被移除。請盡可能根據文字問題回答，並適度提醒使用者切換至視覺模型]\n\n" + user_input

            # ----- 指令功能 -----
            if user_input.startswith("/"):
                handle_cmd(input=user_input, model_object=model, cli=cli, config=config)
                continue # 跳過此次對話
            # -----

            response_streamer = cli.get_response_streamer()

            with cli.get_live() as live: # live 版面 

                for stream_content in model.chat(user_input=user_input, tool_approval=ask_tool_approval, images=images):
                    # ask_tool_approval() 的執行權在 agent.py 上

                    if stream_content.status == "thinking": # 輸出推理內容
                        live.update(cli.render_single_line_streamer(stream_content.content))

                    elif stream_content.status == "thinking_done": # 清除推理內容，輸出推理總結
                        live.update("") # 清除推理內容及隔線
                        cli.console.print(cli.render_thinking_summary(stream_content.think_time))
                        
                    elif stream_content.status == "tool_calling": # 輸出工具參數生成跑馬燈
                        live.update(cli.render_single_line_streamer(stream_content.content))

                    elif stream_content.status == "response": # 輸出模型回答內容
                        response_streamer.update_content(full_text=stream_content.content, live=live)

                    elif stream_content.status == "tool_executed": # 輸出工具調用成功
                        response_streamer.reset(live=live) # 歸零長度記帳，文字不被吞掉
                        cli.console.print(cli.render_tool_approval_result(stream_content.tool_name, True))

                    elif stream_content.status == "tool_rejected": # 輸出工具調用失敗
                        response_streamer.reset(live=live) # 歸零長度記帳，文字不被吞掉
                        cli.console.print(cli.render_tool_approval_result(stream_content.tool_name, False))

                response_streamer.clean(live=live)
    finally:
        clean_ollama(process) # 清除 ollama 進程
