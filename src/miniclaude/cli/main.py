from agent import Agent
from providers.base import LLMResponse
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from dotenv import load_dotenv
from cli.input_prompt import get_input, get_tool_aproval
from cli.renderers import CLIRenderer
from cli.ollama_manager import start_ollama, clean_ollama


load_dotenv()

if __name__ == "__main__":

    model_provider = "Gemini API"
    
    model = Agent(OllamaProvider(model_name="fireboi25/qwythos-v2:q5"))
    color = "blue"
    # -----

    cli = CLIRenderer(model_provider=model_provider, model=model, main_color=color) 

    cli.initialization() # 初始介面

    def ask_tool_approval(tool_name: str):
        live.update("") # 清除分隔線，否則調用許可會出現在分隔線下方
        live.stop() # 停止 live 更新

        try:
            approval = get_tool_aproval(tool_name) # 呼叫取得輸入

        finally:

            live.start() # 重啟 live 更新

        return approval

    process = start_ollama() # 啟動 ollama 進程

    try:

        while True: # 對話迴圈

            user_input = get_input()

            with cli.get_live() as live: # live 版面

                for stream_content in model.chat(user_input=user_input, tool_approval=ask_tool_approval):
                    # ask_tool_approval() 的執行權在 agent.py 上

                    if stream_content.status == "thinking": # 輸出推理內容
                        live.update(cli.render_thinking_content(stream_content.content))

                    elif stream_content.status == "thinking_done": # 清除推理內容，輸出推理總結
                        live.update(cli.render_model_response("")) # 把推理的文字覆蓋掉
                        cli.console.print(cli.render_thinking_summary(stream_content.think_time))
                        
                    elif stream_content.status == "response": # 輸出模型回答內容
                        live.update(cli.render_model_response(stream_content.content))

                    elif stream_content.status == "tool_executed": # 輸出工具調用成功

                        cli.console.print(cli.render_tool_approval_result(stream_content.tool_name, True))

                    elif stream_content.status == "tool_rejected": # 輸出工具調用失敗

                        cli.console.print(cli.render_tool_approval_result(stream_content.tool_name, False))
    finally:
        clean_ollama(process) # 清除 ollama 進程