# data/universe.py
"""通用基础总词库 + 学段筛选规则。

- universe.csv：通用总词库（word, 释义），不区分学段标签，对用户透明。
- stage_words.json：{word: [所属学段...]}，即筛选规则；一个词可属多个学段。
"""
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 5 套内置词本（展示顺序）
STAGES = ["考研", "四级", "六级", "高考", "中考"]

# 科目标签展示顺序（含托福/SAT，用于学习/复习页标注）
STAGE_ORDER = ["中考", "高考", "四级", "六级", "考研", "托福", "SAT"]

_universe: Optional[Dict[str, str]] = None          # {word: trans}
_stage_of_word: Optional[Dict[str, List[str]]] = None  # {word: [stages]}


def _dir() -> Path:
    return Path(__file__).resolve().parent


def load() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """懒加载通用总词库与筛选规则（进程内缓存）。"""
    global _universe, _stage_of_word
    if _universe is None:
        _universe = {}
        with open(_dir() / "universe.csv", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0].strip():
                    _universe[row[0].strip()] = row[1].strip()
        with open(_dir() / "stage_words.json", encoding="utf-8") as f:
            _stage_of_word = json.load(f)
    return _universe, _stage_of_word


def has_word(word: str) -> bool:
    u, _ = load()
    return word in u


def get_trans(word: str) -> Optional[str]:
    u, _ = load()
    return u.get(word)


def get_stages(word: str) -> List[str]:
    """返回单词所属的学段列表（可能多个，可能为空=无内置分类）。"""
    _, s = load()
    return s.get(word, [])


def get_stage_tags(word: str) -> List[str]:
    """返回单词的科目标签（按 STAGE_ORDER 排序），大小写不敏感回退，可为空。"""
    tags = get_stages(word)
    if not tags and word != word.lower():
        tags = get_stages(word.lower())
    if not tags:
        return []
    return sorted(tags, key=lambda t: STAGE_ORDER.index(t) if t in STAGE_ORDER else len(STAGE_ORDER))


def words_of_stage(stage: str) -> Dict[str, str]:
    """返回某学段的全部单词 {word: trans}。"""
    u, s = load()
    return {w: u[w] for w, stages in s.items() if stage in stages}


def total_words() -> int:
    u, _ = load()
    return len(u)
