# Meowgent 🐾

一個輕量、強大且具備人機協同機制的本機 AI Coding Agent CLI 工具。  
支援多模態輸入、獨立子 Agent 分工、上下文智慧壓縮，以及如同 Claude Code 的終端全域執行體驗。

---

## ✨ 核心特色

- **🔒 本地隱私優先**：基於 [Ollama](https://ollama.com/) 本地大語言模型運行，支援思維鏈（Thinking）推理，數據完全保留在自己電腦上。
- **🛠️ 豐富工具生態（MCP / XML 規範）**：
  - 檔案操作：支援檔案讀取 (`read_file`)、建立 (`write_file`)、區塊精準修訂 (`edit_file`) 與目錄遍歷 (`list_file`)。
  - 系統與網路：終端指令執行 (`run_shell`)、文字全文檢索 (`grep_search`) 與網頁內容解析 (`web_fetch`)。
- **👥 子 Agent 協同分工（Sub-agent）**：主模型可指派背景獨立子 Agent 同步執行搜尋或調查任務，並即時回報工作進度與狀態。
- **🖼️ 多模態能力**：支援在對話中附加圖片進行分析與程式碼視覺化討論。
- **🧠 智慧上下文管理**：
  - **即時用量監控**：終端介面實時顯示當前上下文佔比與 Token 消耗。
  - **工具輸出裁剪（Pruning）**：自動修剪歷史輪次過長的工具回傳結果，保留關鍵上下文。
  - **語意結構化壓縮（Compaction）**：超過設定容量自動或手動（`/compact`）呼叫模型提煉「進度筆記」，對話不斷線。
- **🎨 優雅的終端互動介面**：
  - 基於 Rich 的流式 Markdown 渲染與思維鏈折疊展示。
  - 基於 Prompt Toolkit 的語法補全、路徑自動提示、多行輸入與互動式工作目錄選擇器。
- **🛡️ 人機協同審批（Human-in-the-loop）**：可隨時切換工具審核模式（預設詢問、全部同意或嚴格審核），確保終端操作安全可控。

---

## 🚀 安裝與快速開始

### 1. 先備條件

請確保設備已安裝以下先備軟體：

1. **[Ollama](https://ollama.com/)**：下載並啟動，確認已下載指定模型（預設為 `qwen3-vl:4b-thinking`，或自選模型）：
   ```bash
   ollama pull qwen3-vl:4b-thinking
   ```
2. **[uv](https://docs.astral.sh/uv/)**：現代極速 Python 套件管理器
   - macOS / Linux：
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
   - Windows（PowerShell）：
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```

---

### 2. 一鍵安裝 Meowgent

在終端機執行以下指令進行全域安裝：

```bash
uv tool install git+https://github.com/LeeMatthewCat/meowgent.git
```

安裝完成後，在任何目錄下直接輸入即可啟動：

```bash
meowgent
```

---

### 3. 未來版本更新

若專案有新功能釋出，只要執行一行指令即可更新到最新版本：

```bash
uv tool update meowgent
```

---

## 💻 內建斜線指令（Slash Commands）

在對話提示框中輸入 `/` 即可觸發自動補全選單：

| 指令 | 說明 |
| :--- | :--- |
| `/help` | 顯示所有可用指令與說明 |
| `/model` | 即時切換當前已安裝的 Ollama 本地模型 |
| `/config` | 開啟互動式樹狀選單，調整溫度係數、上下文長度、審核模式等設定 |
| `/compact` | 手動觸發對話歷史語意壓縮，將前期歷史提煉為進度筆記 |
| `/cd` | 變更當前工作目錄 |
| `/exit` | 關閉並退出 Meowgent |

---

## ⚙️ 設定檔說明

Meowgent 會在首次啟動時於家目錄自動建立設定檔：`~/.meowgent/config.json`。  
你可以直接透過 `/config` 互動選單調整，或手動修改該檔案：

```json
{
  "models": {
    "default_model": "qwen3-vl:4b-thinking",
    "temperature": 0.1,
    "max_context": 16384
  },
  "sub_agent": {
    "sub_agent_model": "qwen3-vl:4b-thinking",
    "sub_temperature": 0.1
  },
  "agent": {
    "max_turns": 20,
    "tool_approval_mode": "default"
  }
}
```

---

## 🛠️ 開發者指南（本地開發安裝）

若你想修改原始碼或參與開發：

```bash
# 1. 複製專案
git clone https://github.com/LeeMatthewCat/meowgent.git
cd meowgent

# 2. 以可編輯模式安裝到本地工具庫（程式碼修改存檔即時生效）
uv tool install --force --editable .
```

---

## 📁 專案架構

```text
src/meowgent/
 ├── cli/
 │    ├── __init__.py
 │    ├── main.py              # CLI 主程式進入點
 │    ├── commands.py          # 斜線指令註冊與邏輯 (/help, /config 等)
 │    ├── input_prompt.py      # prompt_toolkit 輸入框、補全與多模態圖片附加
 │    ├── renderers.py         # Rich 畫面流式渲染、思維鏈折疊與進度顯示
 │    └── ollama_manager.py    # 本地 Ollama 服務進程生命週期管理
 │
 ├── context/
 │    ├── __init__.py
 │    ├── token.py             # Token 用量估算與圖片 Token 計算
 │    ├── pruner.py            # 工具輸出自動修剪器 (Pruner)
 │    └── compactor.py         # 歷史上下文語意壓縮器 (Compactor)
 │
 ├── config/
 │    ├── __init__.py
 │    ├── config_manager.py    # 設定檔 (~/.meowgent/config.json) 讀寫
 │    ├── config_schema.py     # Pydantic 設定模型定義
 │    └── config_repair.py     # 設定檔自動修復機制
 │
 ├── prompt/
 │    ├── __init__.py
 │    ├── mcp_schema.py        # 工具轉換與 XML Schema 規範
 │    └── system_prompt.py     # 整合動態規則與上下文的 System Prompt 產生器
 │
 ├── providers/
 │    ├── __init__.py
 │    ├── base.py              # 模型供應商抽象介面與資料結構規範
 │    └── ollama_provider.py   # Ollama 串流介接與工具調用實作
 │
 ├── agent.py                  # Agent 核心大腦（對話迴圈、狀態機、工具審核調用）
 └── tool.py                   # 內建工具集 (檔案操作, Shell, 搜尋, Sub-agent 等)
```
