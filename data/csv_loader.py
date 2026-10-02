# data/csv_loader.py
"""CSV 词库导入与内置词本自动导入。"""
import csv

from data.db import get_connection, book_exists
from paths import builtin_csv_dir

# 内置词本：文件名 -> 词本名称（名称固定）
BUILTIN_BOOKS = {
    "level4.csv": "四级核心词汇",
    "level6.csv": "六级核心词汇",
    "kaoyan.csv": "考研核心词汇",
}

_HEADER_KEYS = {'word', '单词', '词汇', 'english', '英文', '单词/词组'}


def _is_header_row(row) -> bool:
    if not row:
        return True
    first = (row[0] or '').strip().lower()
    return first in _HEADER_KEYS


def import_csv(file_path, book_name, skip_header=True, skip_duplicates=True) -> int:
    """
    从 CSV 导入单词到指定词本。
    默认自动跳过表头行、跳过同一词本内重复单词。
    返回成功导入的单词数量。
    """
    conn = get_connection()
    cur = conn.cursor()
    count = 0
    try:
        existing = set()
        if skip_duplicates:
            cur.execute("SELECT word FROM words WHERE book_name = ?", (book_name,))
            existing = {r[0] for r in cur.fetchall()}

        with open(file_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig 自动去 BOM
            reader = csv.reader(f)
            first = True
            for row in reader:
                if not row or len(row) < 2:
                    continue
                if first and skip_header and _is_header_row(row):
                    first = False
                    continue
                first = False
                word = row[0].strip()
                trans = row[1].strip()
                example = row[2].strip() if len(row) >= 3 else ''
                if not word or not trans:
                    continue
                if skip_duplicates and word in existing:
                    continue
                cur.execute(
                    "INSERT INTO words (word, trans, example, book_name, create_day, next_review_day) "
                    "VALUES (?, ?, ?, ?, date('now'), date('now'))",
                    (word, trans, example, book_name),
                )
                existing.add(word)
                count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return count


def import_builtin_wordbooks() -> dict:
    """
    首次运行时自动导入内置词本（已存在的词本跳过）。
    返回 {词本名称: 导入数量}。
    """
    imported = {}
    for filename, book_name in BUILTIN_BOOKS.items():
        if book_exists(book_name):
            continue
        path = builtin_csv_dir() / filename
        if not path.exists():
            continue
        try:
            imported[book_name] = import_csv(str(path), book_name)
        except Exception:
            imported[book_name] = 0
    return imported
