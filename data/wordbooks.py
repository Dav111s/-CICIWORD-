# data/wordbooks.py
"""词本管理：内置词本（只读，由总词库+筛选生成）+ 自定义词本（CRUD）。

表结构：
  wordbooks(name PK, remark, is_builtin)  —— 词本元数据
  words.book_name 关联词本；words.is_builtin 区分只读内置词 / 可编辑自定义词。
"""
from typing import List, Tuple

from data.db import get_connection

BUILTIN_STAGES = ["考研", "四级", "六级", "高考", "中考", "托福", "SAT"]


def init_wordbooks():
    """启动时扫描 7 份 JSON 数据源，清洗合并总词库，并构建 7 套内置只读词本。

    - 原 5 套（考研/四级/六级/高考/中考）内容数量保持不变；新增托福/SAT 两套。
    - 幂等：只新增内置词，绝不删除（保留用户自定义词本 / 收藏 / 全部学习记录）。
    """
    from data import bank
    word_to_trans, stage_map = bank.merge_bank()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wordbooks (
            name TEXT PRIMARY KEY,
            remark TEXT NOT NULL DEFAULT '',
            is_builtin INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(words)").fetchall()}
    if 'is_builtin' not in cols:
        cur.execute("ALTER TABLE words ADD COLUMN is_builtin INTEGER NOT NULL DEFAULT 0")
    conn.commit()

    for stage in BUILTIN_STAGES:
        cur.execute("INSERT OR IGNORE INTO wordbooks (name, remark, is_builtin) VALUES (?, '', 1)", (stage,))
    conn.commit()

    for stage in BUILTIN_STAGES:
        existing = {r[0] for r in cur.execute(
            "SELECT word FROM words WHERE book_name=? AND is_builtin=1", (stage,)).fetchall()}
        for w, stages in stage_map.items():
            if stage in stages and w not in existing:
                cur.execute(
                    "INSERT INTO words (word, trans, book_name, create_day, next_review_day, is_builtin) "
                    "VALUES (?, ?, ?, date('now'), date('now'), 1)",
                    (w, word_to_trans.get(w, ""), stage),
                )
                existing.add(w)
    conn.commit()

    # 控制台日志：输出全部 7 套内置词本各自加载单词数量
    print("[词库初始化] 内置词本加载完成：")
    for stage in BUILTIN_STAGES:
        cnt = cur.execute(
            "SELECT COUNT(*) FROM words WHERE book_name=? AND is_builtin=1", (stage,)).fetchone()[0]
        print(f"  - {stage}：{cnt} 词")

    conn.close()


def list_wordbooks() -> List[Tuple[str, str, int, int]]:
    """返回 [(name, remark, is_builtin, word_count)]，内置在前。"""
    conn = get_connection()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT name, remark, is_builtin FROM wordbooks ORDER BY is_builtin DESC, name").fetchall()
    result = []
    for r in rows:
        cnt = cur.execute("SELECT COUNT(*) FROM words WHERE book_name=?", (r['name'],)).fetchone()[0]
        result.append((r['name'], r['remark'], r['is_builtin'], cnt))
    conn.close()
    return result


def get_words_in_book(name: str) -> List[dict]:
    conn = get_connection()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, word, trans, example FROM words WHERE book_name=? ORDER BY id", (name,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_words(query: str, book_name: str = None, limit: int = 100) -> List[dict]:
    """在「已加载词本」中检索单词（前缀优先 + 释义包含匹配）。

    - 只查 SQLite 的 words 表（即已加载词本），不读 universe.csv 大词库、不遍历文件夹。
    - book_name=None 表示检索全部词本。
    - 返回 [{id, word, trans, book_name}]，前缀命中优先、按 word 排序。
    """
    q = (query or "").strip()
    if not q:
        return []
    conn = get_connection()
    cur = conn.cursor()
    like = f"%{q}%"
    prefix = f"{q}%"
    if book_name:
        cur.execute(
            "SELECT id, word, trans, book_name FROM words "
            "WHERE book_name=? AND (word LIKE ? OR trans LIKE ?) "
            "ORDER BY CASE WHEN word LIKE ? THEN 0 ELSE 1 END, word LIMIT ?",
            (book_name, like, like, prefix, limit),
        )
    else:
        cur.execute(
            "SELECT id, word, trans, book_name FROM words "
            "WHERE word LIKE ? OR trans LIKE ? "
            "ORDER BY CASE WHEN word LIKE ? THEN 0 ELSE 1 END, word LIMIT ?",
            (like, like, prefix, limit),
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------- 自定义词本 CRUD ----------------
def create_wordbook(name: str, remark: str = "") -> bool:
    name = name.strip()
    if not name:
        return False
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO wordbooks (name, remark, is_builtin) VALUES (?, ?, 0)", (name, remark))
    ok = cur.rowcount > 0  # 名称已存在（含内置词本）时 INSERT 被忽略 -> rowcount=0
    conn.commit()
    conn.close()
    return ok


def rename_wordbook(old: str, new: str) -> bool:
    new = new.strip()
    if not new:
        return False
    conn = get_connection()
    cur = conn.cursor()
    # 新名称与其它词本冲突（或未改名）则不执行
    clash = cur.execute(
        "SELECT COUNT(*) FROM wordbooks WHERE name=? AND name!=?", (new, old)).fetchone()[0]
    if clash > 0:
        conn.close()
        return False
    cur.execute("UPDATE wordbooks SET name=? WHERE name=? AND is_builtin=0", (new, old))
    cur.execute("UPDATE words SET book_name=? WHERE book_name=? AND is_builtin=0", (new, old))
    conn.commit()
    conn.close()
    return True


def set_remark(name: str, remark: str):
    conn = get_connection()
    conn.execute("UPDATE wordbooks SET remark=? WHERE name=? AND is_builtin=0", (remark, name))
    conn.commit()
    conn.close()


def delete_wordbook(name: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM wordbooks WHERE name=? AND is_builtin=0", (name,))
    cur.execute("DELETE FROM words WHERE book_name=? AND is_builtin=0", (name,))
    conn.commit()
    conn.close()


def add_word(name: str, word: str, trans: str, example: str = "") -> bool:
    word = word.strip().lower()
    trans = trans.strip()
    if not word or not trans:
        return False
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO words (word, trans, example, book_name, create_day, next_review_day, is_builtin) "
        "VALUES (?, ?, ?, ?, date('now'), date('now'), 0)",
        (word, trans, example, name),
    )
    conn.commit()
    conn.close()
    return True


def add_words_to_book(name: str, items) -> tuple:
    """把 [(word, trans), ...] 追加到指定词本（去重：英文条目已存在则跳过）。

    - 大小写不敏感去重（英文统一小写比较）。
    - 返回 (saved, skipped)：成功写入条数、因重复跳过的条数。
    """
    conn = get_connection()
    cur = conn.cursor()
    existing = {r[0].lower() for r in cur.execute(
        "SELECT word FROM words WHERE book_name=?", (name,)).fetchall()}
    saved = skipped = 0
    for word, trans in items:
        w = (word or '').strip().lower()
        t = (trans or '').strip()
        if not w or not t:
            continue
        if w in existing:
            skipped += 1
            continue
        cur.execute(
            "INSERT INTO words (word, trans, book_name, create_day, next_review_day, is_builtin) "
            "VALUES (?, ?, ?, date('now'), date('now'), 0)",
            (w, t, name))
        existing.add(w)
        saved += 1
    conn.commit()
    conn.close()
    return saved, skipped


def delete_word(word_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM words WHERE id=? AND is_builtin=0", (word_id,))
    conn.commit()
    conn.close()


def update_word(word_id: int, trans: str, example: str = ""):
    conn = get_connection()
    conn.execute("UPDATE words SET trans=?, example=? WHERE id=? AND is_builtin=0", (trans, example, word_id))
    conn.commit()
    conn.close()


def import_csv_to_book(file_path: str, book_name: str) -> int:
    """把 CSV 追加导入到自定义词本（自动创建词本，复用现有 csv_loader，带例句列）。"""
    create_wordbook(book_name)
    from data.csv_loader import import_csv
    return import_csv(file_path, book_name)
