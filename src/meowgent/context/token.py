import re
from typing import Optional

RX_CJK_PATTERN = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]')

def estimate_token(text: str) -> int:
    """ 估算出傳入文字的 token 量 """
    
    # 中日韓文、全形標點
    cjk_count = len(RX_CJK_PATTERN.findall(text))
    
    # 其餘字元（英文、數字、程式碼標點、半形空白等）
    other_chars_count = len(text) - cjk_count

    # 中文每字約 1.3 token，其餘每 3.5 字元約 1 token
    return int((cjk_count * 1.3) + (other_chars_count / 3.5))

def images_token(images: Optional[list[str]] = None):
    """ 估算出圖片的 token 量 """

    if images:
        return 800 * len(images)

    else:
        return 0