from pathlib import Path
from .config_schema import MeowgentConfig
from typing import Tuple, Optional

# 定義位置
CONFIG_DIR = Path.home() / ".meowgent"
CONFIG_FILE = CONFIG_DIR / "config.json"

class ConfigManager():

    @staticmethod
    def save_config(config: MeowgentConfig):

        CONFIG_DIR.mkdir(parents=True, exist_ok=True) # 建立目錄

        json_data = config.model_dump_json(indent=2) # 讀取原始設定格式

        CONFIG_FILE.write_text(json_data, encoding="utf-8") # 寫入設定檔

    @staticmethod
    def load_config(path: Optional[Path] = None) -> Tuple[bool, MeowgentConfig]:
        path = path if path is not None else CONFIG_FILE

        if not path.exists(): # 設定檔不存在 -> 建立設定檔

            config = MeowgentConfig() # 獲取預設設定
            ConfigManager.save_config(config)

            return (True, config)

        else: # 設定檔存在

            try:
                content = path.read_text(encoding="utf-8")

                config = MeowgentConfig.model_validate_json(content) # 讀取到的 JSON（字串形式）載入模型（MeowgentConfig）
                ConfigManager.save_config(config) # 若有新設定更新進 JSON 檔

                return (True, config)

            except Exception: # 讀取錯誤時

                return (False, MeowgentConfig())