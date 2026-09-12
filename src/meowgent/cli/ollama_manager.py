import subprocess
import httpx
import time
from typing import Tuple, Optional

def start_ollama() -> Tuple[bool, Optional[subprocess.Popen]]:

    try:
        httpx.get("http://localhost:11434", timeout=1) # 檢查是否已經有連線
        return (True, None)

    except httpx.ConnectError: # 未連線 -> 嘗試連線

        try:
            process = subprocess.Popen(
                args=["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL # 捨棄終端輸出
            )
        except Exception: # 攔截沒裝 ollama、權限不足等
            return (False, None)

        for _ in range(20):
            if process.poll() is not None: # 專端指令已崩潰
                return (False, None)

            try:
                httpx.get("http://localhost:11434", timeout=1)

                return (True, process) # 成功連線

            except httpx.ConnectError:
                time.sleep(0.5) # 還未現成功，等待

        clean_ollama(process)
        return (False, None) # 嘗試 20 次還是沒有連線

def clean_ollama(process: Optional[subprocess.Popen]):
    if process and process.poll() is None: # 確保 ollama 程序還在跑
        process.terminate() # 清理進程

        process.wait() # 等待終止