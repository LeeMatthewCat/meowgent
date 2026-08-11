# 架構
```
src/miniclaude/
 ├── providers
 |    ├── __init__.py
 |    ├── base.py                  # 規範
 |    ├── gemini/ollama_provider
 ├── providers/
 ├── agent.py
 ├── tool.py
 └── cli/                          # 建立一個專屬的 UI 資料夾
      ├── __init__.py
      ├── main.py                  # 進入點
      ├── input_prompt.py          # 專門負責 prompt_toolkit 的輸入框
      └── renderers.py             # 專門負責 rich 的畫面渲染 (渲染 -> 畫框框、畫進度條)
```

# 畫面預想：
```

  MeowCode CLI 1.0 -> 主色調
  matthew -> 灰

———————————————————————————————————————————
> 使用者輸入 -> 主色調

回答
———————————————————————————————————————————
```


# 檢查：
1. gemini：推理尚未測試，在 agent.py 和 agent_.py
2. ollama 使用 system prompt 層面注入工具調用規範，不使用自帶工具調用接口，提升效能


