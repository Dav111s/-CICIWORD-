# data/bank.py
"""通用总词库清洗合并（代码内完成，不再用独立脚本）。

- 读取 data/builtin 下 7 份 JSON 词库（1-初中 ~ 7-SAT 顺序.json）；
- 与现有 universe.csv 对比，只把不存在的新词追加进总词库，保留全部旧词条，执行去重；
- 生成/更新 universe.csv 与 stage_words.json（7 类科目标签）。
"""
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

_BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"
_DATA_DIR = Path(__file__).resolve().parent

# 7 份 JSON 数据源 -> 科目标签（前 5 套对应内置只读学段词本：中考/高考/四级/六级/考研）
JSON_SOURCES = [
    ("1-初中-顺序.json", "中考"),
    ("2-高中-顺序.json", "高考"),
    ("3-CET4-顺序.json", "四级"),
    ("4-CET6-顺序.json", "六级"),
    ("5-考研-顺序.json", "考研"),
    ("6-托福-顺序.json", "托福"),
    ("7-SAT-顺序.json", "SAT"),
]

# 单词：字母开头，可含连字符/撇号，不含空格（排除多词短语）
_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'’\-]*$")
_TYPE_RE = re.compile(r"^[A-Za-z]{1,6}\.?$")


def _clean_trans(translations) -> str:
    """把 translations 列表清洗为「type. 释义；type. 释义」字符串。"""
    parts = []
    for t in translations or []:
        tt = re.sub(r"\s+", " ", (t.get("translation") or "").strip())
        ty = (t.get("type") or "").strip()
        ty = ty if (ty and _TYPE_RE.match(ty)) else ""
        if tt:
            parts.append(f"{ty}. {tt}" if ty else tt)
    return "；".join(parts)


def _iter_json_words(path) -> Tuple[str, str]:
    """逐条读取一份 JSON 词库，yield (word, trans)。只取单词，跳过短语/多词。"""
    data = json.load(open(path, encoding="utf-8"))
    for it in data:
        w = (it.get("word") or "").strip()
        if not _WORD_RE.match(w):
            continue
        yield w, _clean_trans(it.get("translations"))


def scan_sources() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """扫描 7 份 JSON 数据源，返回 (word->trans, word->[stage标签])。"""
    word_to_trans: Dict[str, str] = {}
    stage_map: Dict[str, List[str]] = {}
    for filename, stage in JSON_SOURCES:
        for w, trans in _iter_json_words(_BUILTIN_DIR / filename):
            if w not in word_to_trans or len(trans) > len(word_to_trans[w]):
                word_to_trans[w] = trans
            tags = stage_map.setdefault(w, [])
            if stage not in tags:
                tags.append(stage)
    return word_to_trans, stage_map


def merge_bank() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """清洗合并：扫描 7 份 JSON + 现有 universe.csv，写回 universe.csv 与 stage_words.json。

    - 只追加 universe.csv 中不存在的新词，保留全部旧词条，去重；
    返回 (合并后的 word->trans, word->[stage标签])。
    """
    src_trans, stage_map = scan_sources()

    # 现有 universe.csv（旧词条，全部保留）
    existing: Dict[str, str] = {}
    csv_path = _DATA_DIR / "universe.csv"
    if csv_path.exists():
        with open(csv_path, encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0].strip():
                    existing[row[0].strip()] = row[1].strip()

    # 合并：旧词保留，新词追加
    merged = dict(existing)
    for w, t in src_trans.items():
        if w not in merged:
            merged[w] = t

    # 写回 universe.csv（去重 + 排序）
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        for w in sorted(merged):
            wr.writerow([w, merged[w]])

    # 重建 stage_words.json（只保留 universe 中出现的词）
    stage_only = {w: stage_map[w] for w in merged if w in stage_map}
    with open(_DATA_DIR / "stage_words.json", "w", encoding="utf-8") as f:
        json.dump(stage_only, f, ensure_ascii=False)

    return merged, stage_map
