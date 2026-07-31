import os
from dotenv import load_dotenv
from google import genai
import ollama
from rich.console import Console
from rich.markdown import Markdown
import questionary
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider
from tool import execute_tool, TOOL_REGISTRY
from providers.base import LLMProvider, ToolCall
import time
from rich.live import Live
from typing import List

load_dotenv() # 載入 .env 檔內的環境變數

console = Console() # 初始化 rich 終端

if __name__ == "__main__":

    # ========== A. 選擇模型 ==========
    model_from = questionary.select(
        "選擇模型供應商：",
        choices=["Google Gemini", "本地模型"]
    ).ask()

    if model_from == "Google Gemini":
        # ----- 1. 選擇模型 -----
        model_name = "gemini-3.5-flash-lite"

        # ----- 2. 初始化調用接口 -----
        provider = GeminiProvider(model_name)

    elif model_from == "本地模型":
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
            ) # 使用者輸入加入多輪
        # -----

            while True: # 呼叫模型

                # ----- 1. 初始化 -----
                response = provider.stream_generate(history_messages=history_messages)

                thinking_full_text = "💭 "
                result_full_text = "🤖 "

                is_thinking = False
                think_time = None

                tools: List[ToolCall] = []

                # ----- 2. 向模型索取串流片段 -----
                with Live(console=console, refresh_per_second=10, vertical_overflow="visible") as live:
                    def thinking_finish():
                        """ 判斷推理階段是否結束，若結束則清除版面並顯示推理時間 """
                        global is_thinking, think_time

                        if is_thinking: # 表示為推理結束後進到回答或工具調用階段
                            live.update(Markdown("")) # 清除推理過程
                            # 因為 live.update("") 會有高度為 1 的空白，而 tool use 部分的 console.input() 顯示的並不會把 live 覆蓋
                            # 所以用 Markdown("") 可確保渲染高度為 0，避免在工具調用時留下空行

                            think_time = round(time.perf_counter() - think_time, 1) # 更新計時
                            console.print(f"💭 [bold blue]已思考 {think_time} 秒...[/bold blue]")

                            is_thinking = False

                    for chunk in response:

                        if chunk.thinking_chunk:
                            is_thinking = True
                            think_time = time.perf_counter() if think_time is None else think_time # 如果沒開始計時（此次推理第一個 token 出現時）開始計時

                            # 流式輸出
                            thinking_full_text += chunk.thinking_chunk
                            live.update(Markdown(thinking_full_text))

                        if chunk.content_chunk:
                            thinking_finish()

                            # 流式輸出
                            result_full_text += chunk.content_chunk
                            live.update(Markdown(result_full_text))

                        if chunk.tool_calls:
                            thinking_finish()

                            live.update(Markdown(""))

                            tools.extend(chunk.tool_calls) # 把函數名和參數扁平的傳入（讓傳入的串列扁平化，不要 tools 的串列包 chunk.tool_call 的串列）

                # ----- 3. tool use -----
                if tools: # 表示有 tool use 需求

                    history_messages.append(
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "name": t.tool_name,
                                    "args": t.args,
                                    "id": getattr(t, "id", None),
                                    "thought_signature": getattr(t, "thought_signature", None)
                                } for t in tools
                            ]
                        }
                    ) # 呼叫工具的訊息加入多輪

                    for t in tools:
                        # t 為 ToolCall 型別物件

                        f = TOOL_REGISTRY.get(t.tool_name, None)

                        if f and getattr(f, "need_approval", True): # 函數存在且需要調用許可
                            # 不直接 f.need_approval 避免工具沒有註明調用許可（沒註明則強制取得使用者同意）

                            approval = console.input(f"❓ [bold blue]是否允許模型調用 {t.tool_name}（y/n）[/bold blue]")

                            if approval.strip().lower() != "y": # tool use 調用被拒絕
                                # 不分大小寫、去除前後空白

                                history_messages.append(
                                    {
                                        "role": "tool",
                                        "tool_name": t.tool_name,
                                        "id": getattr(t, "id", None),
                                        "content": f"User rejected execution of this tool for security reasons"
                                    }
                                ) # 工具調用失敗的訊息加入多輪

                                console.print("❕ [bold blue]此工具調用已被拒絕[/bold blue]")
                                continue # 進到下一個 for t in tools: 迴圈（看下一個調用）或直接進到迴圈下面（迴圈已結束）

                        history_messages.append(
                            {
                                "role": "tool",
                                "tool_name": t.tool_name,
                                "id": getattr(t, "id", None),
                                "content": execute_tool(tool_name=t.tool_name, tool_args=t.args)
                            }
                        ) # 成功調用工具的訊息加入多輪

                        console.print(f"🔧 {t.tool_name} [bold blue]已被調用[/bold blue]")

                else: # 沒有 tool use
                    result_full_text = result_full_text[2:] # "🤖 " 切除
                    if not result_full_text.strip():
                        result_full_text = "（模型沒有回傳內容）"
                    
                    history_messages.append(
                        {
                            "role": "assistant",
                            "content": result_full_text
                        }
                    ) # 對話加入多輪

                    break # 模型沒有調用工具 -> 表示已經生成最終回答，故退出 while True: 迴圈
