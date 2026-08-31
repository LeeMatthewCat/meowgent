from agent import Agent
from providers import LLMResponse, GeminiProvider, OllamaProvider
from dotenv import load_dotenv
from cli import get_input, get_tool_aproval, CLIRenderer, start_ollama, clean_ollama, handle_cmd, select_directory
import os

load_dotenv() # 讀取 .env

if __name__ == "__main__":

    model_name = "fireboi25/qwythos-v2:q5"

    # ----- 初始化模型 ----
    
    model = Agent(OllamaProvider(model_name=model_name))

    path = select_directory()
    model.renew_system_prompt(
        rule=None, # 採用預設規則
        model_name=model_name,
        path=path
    )
    # -----

    os.chdir(path)

    cli = CLIRenderer() 

    cli.initialization() # 初始介面

    process = start_ollama() # 啟動 ollama 進程

    def ask_tool_approval(tool_name: str, tool_args: dict) -> bool:
        live.update("") # 清除分隔線，否則調用許可會出現在分隔線下方
        live.stop() # 停止 live 更新

        try:
            approval = get_tool_aproval(tool_name, tool_args) # 呼叫取得輸入

        finally:

            live.start() # 重啟 live 更新

        return approval

    try:

        while True: # 對話迴圈

            user_input = get_input().strip()
            # .strip() 清除頭尾的空格、換行符號、製表符（做表格用的），杜絕 / 指令誤判

            if not user_input: # 擋住空字串傳入
                continue

            # ----- 指令功能 -----
            if user_input.startswith("/"):
                handle_cmd(input=user_input, model_object=model, cli=cli)
                continue # 跳過此次對話
            # -----

            with cli.get_live() as live: # live 版面

                response_streamer = cli.get_response_streamer()

                for stream_content in model.chat(user_input=user_input, tool_approval=ask_tool_approval):
                    # ask_tool_approval() 的執行權在 agent.py 上

                    if stream_content.status == "thinking": # 輸出推理內容
                        live.update(cli.render_single_line_streamer(stream_content.content))

                    elif stream_content.status == "thinking_done": # 清除推理內容，輸出推理總結
                        live.update("") # 清空跑馬燈，絕不留幽靈橫線
                        cli.console.print(cli.render_thinking_summary(stream_content.think_time))
                        
                    elif stream_content.status == "tool_calling": # 輸出工具參數生成跑馬燈
                        live.update(cli.render_tool_calling_streamer(stream_content.content))

                    elif stream_content.status == "response": # 輸出模型回答內容
                        response_streamer.update_content(full_text=stream_content.content, live=live)

                    elif stream_content.status == "tool_executed": # 輸出工具調用成功
                        response_streamer.reset(live=live) # 歸零長度記帳，確保第二輪開頭文字不被吞掉
                        cli.console.print(cli.render_tool_approval_result(stream_content.tool_name, True))

                    elif stream_content.status == "tool_rejected": # 輸出工具調用失敗
                        response_streamer.reset(live=live) # 歸零長度記帳
                        cli.console.print(cli.render_tool_approval_result(stream_content.tool_name, False))

                response_streamer.clean(live=live)
    finally:
        clean_ollama(process) # 清除 ollama 進程