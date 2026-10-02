# data/word_matcher.py
"""批量单词清洗 + 识别匹配。"""
import re
from typing import List, Tuple

from data import universe


def clean_words(text: str) -> List[str]:
    """清洗文本：按空白/标点切分，转小写，去重（保留首次出现顺序）。"""
    words = re.split(r"[^A-Za-z'\-]+", text or "")
    seen = set()
    result = []
    for w in words:
        w = w.strip().strip("'-")
        if w and w.lower() not in seen:
            seen.add(w.lower())
            result.append(w.lower())
    return result


def recognize(text: str) -> List[Tuple[str, str, List[str]]]:
    """
    批量识别。返回 [(word, trans, stages)]。
    - 在总词库中：trans 有值，stages 为其所属学段列表（可为空）。
    - 不在总词库：trans 为 None，stages 为空 -> 前端标记【无内置分类】。
    """
    result = []
    for w in clean_words(text):
        trans = universe.get_trans(w)
        stages = universe.get_stages(w) if trans is not None else []
        result.append((w, trans, stages))
    return result
