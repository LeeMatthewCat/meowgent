# 架構
```
src/meowgent/
 ├── providers
 |    ├── __init__.py
 |    ├── base.py                  # 規範
 |    └── gemini_provider.py
 |    └── ollama_provider.py
 |
 ├── prompt/
 |    ├── __init__.py
 |    ├── mcp_schema.py            # 1. 轉換內部工具 2. 外部插件做格式驗證
 |    └── system_prompt.py         # 1. 把 MCP 格式做打包合併 2. 將所有提示詞整合餵給模型
 |
 ├── agent.py
 ├── tool.py
 └── cli/
      ├── __init__.py
      ├── main.py                  # 進入點
      ├── input_prompt.py          # 專門負責 prompt_toolkit 的輸入框
      ├── renderers.py             # 專門負責 rich 的畫面渲染 (渲染 -> 畫框框、畫進度條)
      └── commands.py
```

# 畫面預想：
```

  Meowgent CLI 1.0 -> 主色調
  matthew -> 灰

———————————————————————————————————————————
> 使用者輸入 -> 主色調

回答
———————————————————————————————————————————
```


# 檢查：
1. gemini：推理尚未測試，在 agent.py 和 agent_.py
2. ollama 使用 system prompt 層面注入工具調用規範，不使用自帶工具調用接口，提升效能




