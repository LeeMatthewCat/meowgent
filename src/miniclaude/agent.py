import os
from dotenv import load_dotenv
from google import genai
import ollama
from rich.console import Console
from rich.markdown import Markdown
from rich.markdown import Markdown
import questionary
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from tool import execute_tool, TOOL_REGISTRY

load_dotenv() # 載入 .env 檔內的環境變數

console = Console() # 初始化 rich 終端

if __name__ == "__main__":

    # ========== A. 選擇模型 ==========
    modle_from = questionary.select(
        "選擇模型供應商：",
        choices=["Google Gemini", "本地模型"]
    ).ask()

    if modle_from == "Google Gemini":
        # ----- 1. 選擇模型 -----
        model_name = "gemini-2.5-flash"

        # ----- 2. 初始化調用接口 -----
        provider = GeminiProvider(model_name)

    elif modle_from == "本地模型":
        model_name = questionary.select(
            "選擇本地模型：",
            choices=[i.model for i in ollama.list().models]
        ).ask()

        provider = OllamaProvider(model_name)
        

    # ========== B. 對話迴圈 ==========
    history_messages = [] # 多倫對話歷史

    while True: # 對話回圈

        user_input = console.input("🔎 [bold blue]輸入對話...[/bold blue]") # 接受輸入

        # ----- 離開對話 -----
        if user_input == "q":
            break # 終止對話
        else:
            history_messages.append(
                {
                    "role": "user",
                    "content": user_input
                }
            )
        # -----

            while True: # 呼叫模型

                response = provider.generate(history_messages)

                if response.tool_calls: # 調用工具

                    tool_call_result = "execute tool result:"
                    for t in response.tool_calls:

                        func = TOOL_REGISTRY.get(t.tool_name)
                        if func and func.need_approval is True: # 函數存在且需要調用許可時
                            approval = console.input(f"❓ [bold blue]是否允許模型調用 {t.tool_name} [y/n][/bold blue]")

                            if approval.strip().lower() != "y": # tool use 調用被拒絕
                                # 不分大小寫、去除前後空白

                                tool_call_result += f"User rejected execution of {t.tool_name} for security reasons" + "\n"
                                console.print("❕ [bold blue]此工具調用已被拒絕[/bold blue]")
                                continue # 進到下一個 for t 迴圈（看下一個調用）或直接進到迴圈下面（迴圈已結束）

                        tool_call_result += (f"{t.tool_name} return:" + execute_tool(
                            tool_name=t.tool_name,
                            tool_args=t.args
                        ) + "\n") 

                    history_messages.append(
                        {
                            "role": "tool",
                            "content": tool_call_result
                        }
                    ) # 工具加到多倫對話紀錄
                else:
                    break # 不再調用工具（模型已給出回答）則終止迴圈

            # ----- 印出對話 -----
            # 因為 gemini 流式對話尚未實作
            console.print(Markdown(response.content if response.content else "⚠️錯誤：輸入或輸出內容可能觸發資安／敏感過濾機制")) if modle_from != "本地模型" else ...
            # 第一個 if 防止 response.content 為 None
            # 第二個 if 因為 ollama 有流式輸出

            history_messages.append(
                {
                    "role": "assistant",
                    "content": response.content
                }
            ) # 回覆加到多倫對話紀錄


    





