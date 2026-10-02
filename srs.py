# srs.py
"""SRS 间隔重复模块（增量新增，不重构既有 word_app 逻辑）。

职责边界：本模块只负责【记忆概率、复习间隔、答题历史】；
单词释义/例句/辨析交给 RAG 与词库模块，这里不处理。

两套实现（输入输出语义完全一致，可无缝切换）：
  V1  simulate_three_feedback(...)     启发式模拟（默认，无神经网络）
  V2  neural_srs_model.predict(dict)   神经网络推理占位（MLP 入口，后续替换真实网络）

数据库：
  srs_records  每词一行：memory_prob / ease / last_review_ts / next_review_ts / history_ids(json)
  srs_history  每次答题一行：只存特征，不重复存释义（供本地离线训练）
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ============================ 枚举 ============================
class ReviewFeedback(str, Enum):
    """三档答题反馈。"""
    REMEMBER = "remember"   # 记住：看到单词快速反应释义
    HAZY = "hazy"           # 模糊：有印象但记不准释义
    FORGET = "forget"       # 忘记：完全没印象


# ============================ 常量 ============================
MIN_INTERVAL_SECONDS = 60                       # 最小间隔
MAX_INTERVAL_SECONDS = 60 * 60 * 24 * 365       # 最大间隔 1 年
PROB_FLOOR = 0.05                               # memory_prob 下限
PROB_CEIL = 0.95                                # memory_prob 上限
MIN_EASE = 1.0
MAX_EASE = 5.0
DEFAULT_PROB = 0.5
DEFAULT_EASE = 2.5
INTERVAL_BASE_DAYS = 180                        # prob_to_interval 基准天数
DEFAULT_DB = "srs.db"


# ============================ 数据模型 ============================
@dataclass
class SrsRecord:
    record_id: str
    word: str
    memory_prob: float = DEFAULT_PROB
    ease: float = DEFAULT_EASE
    last_review_ts: int = 0                      # 0 表示新单词
    next_review_ts: int = 0
    history_ids: List[str] = field(default_factory=list)


@dataclass
class SrsHistory:
    """单次答题特征，只存特征，不存完整释义。"""
    record_id: str
    word: str
    feedback: str
    time_delta: float
    old_memory_prob: float
    old_ease: float
    word_freq: float
    timestamp: int


# ============================ 工具 ============================
def _clamp_prob(p: float) -> float:
    return max(PROB_FLOOR, min(PROB_CEIL, p))


def _clamp_ease(e: float) -> float:
    return max(MIN_EASE, min(MAX_EASE, e))


def _fb(fb) -> str:
    return fb.value if isinstance(fb, ReviewFeedback) else str(fb)


# ============================ 核心函数 ============================
def prob_to_interval(prob: float, ease: float) -> int:
    """记忆概率(0~1) + 难度系数 -> 复习间隔(秒)。

    interval_days = ease * INTERVAL_BASE_DAYS * prob^3
    高 prob、高 ease -> 长间隔；低 prob -> 短间隔。
    结果钳位到 [60s, 1年]。
    """
    p = _clamp_prob(prob)
    e = _clamp_ease(ease)
    days = e * INTERVAL_BASE_DAYS * (p ** 3)
    secs = int(days * 86400)
    return max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, secs))


def simulate_three_feedback(old_prob: float, old_ease: float, feedback: ReviewFeedback) -> Tuple[float, float]:
    """V1 启发式模拟。返回 (new_memory_prob, new_ease)。

    模糊(HAZY)的核心：概率适度下调、ease 小衰减——间隔比"记住"短、比"忘记"长。
    """
    p = _clamp_prob(old_prob)
    e = _clamp_ease(old_ease)

    if feedback == ReviewFeedback.REMEMBER:
        new_p = p + (PROB_CEIL - p) * 0.30
        new_e = e * 1.15
    elif feedback == ReviewFeedback.HAZY:
        new_p = p * 0.85
        new_e = e * 0.95
    else:  # FORGET
        new_p = p * 0.50
        new_e = e * 0.85

    return _clamp_prob(new_p), _clamp_ease(new_e)


class NeuralSrsModel:
    """V2 神经网络推理占位（MLP 入口）。

    predict(model_input: dict) -> (new_memory_prob, new_ease)
    输入 dict 含：feedback / time_delta / old_memory_prob / old_ease / word_freq。
    输入输出语义与 simulate_three_feedback 一致，后期替换真实网络即可。
    未接入网络时内部回退 V1，保证可运行。
    """

    def __init__(self):
        self._net = None  # TODO: 加载 MLP 权重

    def predict(self, model_input: Dict[str, Any]) -> Tuple[float, float]:
        fb = model_input.get("feedback")
        old_prob = float(model_input.get("old_memory_prob", DEFAULT_PROB))
        old_ease = float(model_input.get("old_ease", DEFAULT_EASE))
        # TODO: 真实网络可额外使用 time_delta / word_freq 等特征
        feedback = fb if isinstance(fb, ReviewFeedback) else ReviewFeedback(fb)
        return simulate_three_feedback(old_prob, old_ease, feedback)


neural_srs_model = NeuralSrsModel()


# ============================ SQLite 存储层 ============================
def get_conn(db_path: str = DEFAULT_DB):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_srs_schema(db_path: str = DEFAULT_DB):
    """建表 + 为旧 srs_records 增量补列（幂等）。"""
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS srs_records (
            record_id TEXT PRIMARY KEY,
            word TEXT NOT NULL,
            memory_prob REAL NOT NULL DEFAULT 0.5,
            ease REAL NOT NULL DEFAULT 2.5,
            last_review_ts INTEGER NOT NULL DEFAULT 0,
            next_review_ts INTEGER NOT NULL DEFAULT 0,
            history_ids TEXT NOT NULL DEFAULT '[]'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS srs_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL,
            word TEXT NOT NULL,
            feedback TEXT NOT NULL,
            time_delta REAL NOT NULL,
            old_memory_prob REAL NOT NULL,
            old_ease REAL NOT NULL,
            word_freq REAL NOT NULL,
            timestamp INTEGER NOT NULL
        )
    """)
    cols = {r[1] for r in cur.execute("PRAGMA table_info(srs_records)").fetchall()}
    if "last_review_ts" not in cols:
        cur.execute("ALTER TABLE srs_records ADD COLUMN last_review_ts INTEGER NOT NULL DEFAULT 0")
    if "history_ids" not in cols:
        cur.execute("ALTER TABLE srs_records ADD COLUMN history_ids TEXT NOT NULL DEFAULT '[]'")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_srs_history_record ON srs_history(record_id)")
    conn.commit()
    conn.close()


def load_srs_record(record_id: str, db_path: str = DEFAULT_DB) -> Optional[SrsRecord]:
    conn = get_conn(db_path)
    row = conn.execute("SELECT * FROM srs_records WHERE record_id = ?", (record_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return SrsRecord(
        record_id=row["record_id"],
        word=row["word"],
        memory_prob=row["memory_prob"],
        ease=row["ease"],
        last_review_ts=row["last_review_ts"],
        next_review_ts=row["next_review_ts"],
        history_ids=json.loads(row["history_ids"] or "[]"),
    )


def _ensure_record(db_path: str, r: SrsRecord):
    conn = get_conn(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO srs_records (record_id, word, memory_prob, ease, last_review_ts, next_review_ts, history_ids) "
        "VALUES (?,?,?,?,?,?,?)",
        (r.record_id, r.word, r.memory_prob, r.ease, r.last_review_ts, r.next_review_ts, json.dumps(r.history_ids)),
    )
    conn.commit()
    conn.close()


def _insert_history(db_path: str, h: SrsHistory) -> str:
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO srs_history (record_id, word, feedback, time_delta, old_memory_prob, old_ease, word_freq, timestamp) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (h.record_id, h.word, h.feedback, h.time_delta, h.old_memory_prob, h.old_ease, h.word_freq, h.timestamp),
    )
    conn.commit()
    hid = str(cur.lastrowid)
    conn.close()
    return hid


def _update_record(db_path: str, r: SrsRecord):
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE srs_records SET word=?, memory_prob=?, ease=?, last_review_ts=?, next_review_ts=?, history_ids=? "
        "WHERE record_id=?",
        (r.word, r.memory_prob, r.ease, r.last_review_ts, r.next_review_ts, json.dumps(r.history_ids), r.record_id),
    )
    conn.commit()
    conn.close()


# ============================ 主处理函数 ============================
def process_review_feedback(
    srs_record: SrsRecord,
    feedback: ReviewFeedback,
    word_freq: float,
    now_ts: Optional[int] = None,
    db_path: str = DEFAULT_DB,
    use_neural: bool = False,
) -> SrsRecord:
    """处理一次三档答题反馈，更新记忆状态并写库。返回更新后的 SrsRecord。

    use_neural=False -> V1 启发式；use_neural=True -> V2 神经网络占位。
    """
    now_ts = now_ts if now_ts is not None else int(time.time())

    # 1. time_delta（新单词 last_review_ts=0 特殊处理，不能直接相减）
    if srs_record.last_review_ts == 0:
        time_delta = 0.0
    else:
        time_delta = float(max(0, now_ts - srs_record.last_review_ts))

    old_prob = _clamp_prob(srs_record.memory_prob)
    old_ease = _clamp_ease(srs_record.ease)

    # 2. 组装模型输入并推理
    if use_neural:
        model_input = {
            "feedback": feedback,
            "time_delta": time_delta,
            "old_memory_prob": old_prob,
            "old_ease": old_ease,
            "word_freq": float(word_freq),
        }
        new_prob, new_ease = neural_srs_model.predict(model_input)
    else:
        new_prob, new_ease = simulate_three_feedback(old_prob, old_ease, feedback)

    # 3. 钳位 + 间隔 + 下次复习时间
    new_prob = _clamp_prob(new_prob)
    new_ease = _clamp_ease(new_ease)
    interval = prob_to_interval(new_prob, new_ease)
    next_review_ts = now_ts + interval

    # 4. 写历史
    init_srs_schema(db_path)
    _ensure_record(db_path, srs_record)
    history = SrsHistory(
        record_id=srs_record.record_id,
        word=srs_record.word,
        feedback=_fb(feedback),
        time_delta=time_delta,
        old_memory_prob=old_prob,
        old_ease=old_ease,
        word_freq=float(word_freq),
        timestamp=now_ts,
    )
    history_id = _insert_history(db_path, history)

    # 5. 更新 SrsRecord 并写库
    srs_record.memory_prob = new_prob
    srs_record.ease = new_ease
    srs_record.last_review_ts = now_ts
    srs_record.next_review_ts = next_review_ts
    srs_record.history_ids.append(history_id)
    _update_record(db_path, srs_record)

    return srs_record


# ============================ Demo ============================
if __name__ == "__main__":
    import tempfile, os
    db = os.path.join(tempfile.mkdtemp(), "srs.db")
    init_srs_schema(db)

    r = SrsRecord(record_id="w1", word="apple")  # 新单词，last_review_ts=0
    for fb in (ReviewFeedback.REMEMBER, ReviewFeedback.HAZY, ReviewFeedback.FORGET):
        r = process_review_feedback(r, fb, word_freq=0.6, db_path=db)
        interval_days = (r.next_review_ts - r.last_review_ts) / 86400
        print(f"{fb.value:8s} -> prob={r.memory_prob:.3f} ease={r.ease:.2f} interval={interval_days:.1f}d")

    # 校验历史记录
    conn = get_conn(db)
    n = conn.execute("SELECT COUNT(*) FROM srs_history").fetchone()[0]
    print("srs_history rows:", n)
    conn.close()
