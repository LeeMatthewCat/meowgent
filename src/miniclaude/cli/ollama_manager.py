import subprocess
import httpx
import time
from typing import Optional

def start_ollama() -> Optional[subprocess.Popen]:

    try:
        httpx.get("http://localhost:11434", timeout=1) # 檢查是否已經有連線
        return None

    except httpx.ConnectError: # 未連線 -> 嘗試連線

        process = subprocess.Popen(
            args=["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL # 捨棄終端輸出
        )

        while True:
            try:
                httpx.get("http://localhost:11434", timeout=1)

                break # 成功連線

            except httpx.ConnectError:
                time.sleep(0.5) # 還未現成功，等待

        return process

def clean_ollama(process: Optional[subprocess.Popen]):
    if process:
        process.terminate() # 清理進程

        process.wait() # 等待清理