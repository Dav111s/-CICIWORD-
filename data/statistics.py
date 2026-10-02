# data/statistics.py
"""学习统计计算（总数、掌握度、每日正确率趋势、遗忘曲线、拼写测试）。"""
from datetime import datetime, timedelta

from data.db import get_connection


def get_total_words_count(book_name=None):
    conn = get_connection()
    cur = conn.cursor()
    if book_name:
        cur.execute("SELECT COUNT(*) FROM words WHERE book_name = ?", (book_name,))
    else:
        cur.execute("SELECT COUNT(*) FROM words")
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_today_review_count(book_name=None):
    """今日到期待复习单词数。"""
    conn = get_connection()
    cur = conn.cursor()
    if book_name:
        cur.execute(
            "SELECT COUNT(*) FROM words WHERE next_review_day <= date('now') AND book_name = ?",
            (book_name,),
        )
    else:
        cur.execute("SELECT COUNT(*) FROM words WHERE next_review_day <= date('now')")
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_new_words_count(book_name=None):
    """未学习的新单词数（records 中无记录）。"""
    conn = get_connection()
    cur = conn.cursor()
    sql = """
        SELECT COUNT(*) FROM words w
        LEFT JOIN records r ON w.id = r.word_id
        WHERE r.id IS NULL
    """
    if book_name:
        sql += " AND w.book_name = ?"
        cur.execute(sql, (book_name,))
    else:
        cur.execute(sql)
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_learned_words_count(book_name=None):
    """已学习单词数（records 中有记录的去重单词数）。"""
    conn = get_connection()
    cur = conn.cursor()
    sql = """
        SELECT COUNT(DISTINCT r.word_id)
        FROM records r JOIN words w ON r.word_id = w.id
    """
    if book_name:
        sql += " WHERE w.book_name = ?"
        cur.execute(sql, (book_name,))
    else:
        cur.execute(sql)
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_mastered_words_count(book_name=None):
    """已掌握单词数：末尾连续答对 >= 3 次的单词数。"""
    conn = get_connection()
    cur = conn.cursor()
    sql = """
        SELECT r.word_id, r.is_right
        FROM records r JOIN words w ON r.word_id = w.id
    """
    if book_name:
        sql += " WHERE w.book_name = ?"
    sql += " ORDER BY r.id"
    if book_name:
        cur.execute(sql, (book_name,))
    else:
        cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    streak = {}
    for word_id, is_right in rows:
        streak[word_id] = streak.get(word_id, 0) + 1 if is_right else 0
    return sum(1 for s in streak.values() if s >= 3)


def get_today_study_count(book_name=None):
    """今日学习数量（record_type='learn'）。"""
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    sql = """
        SELECT COUNT(*) FROM records r JOIN words w ON r.word_id = w.id
        WHERE r.record_type='learn' AND r.review_day = ?
    """
    if book_name:
        sql += " AND w.book_name = ?"
        cur.execute(sql, (today, book_name))
    else:
        cur.execute(sql, (today,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_today_reviewed_count(book_name=None):
    """今日复习数量（record_type='review'）。"""
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    sql = """
        SELECT COUNT(*) FROM records r JOIN words w ON r.word_id = w.id
        WHERE r.record_type='review' AND r.review_day = ?
    """
    if book_name:
        sql += " AND w.book_name = ?"
        cur.execute(sql, (today, book_name))
    else:
        cur.execute(sql, (today,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_accuracy_trend(days=7, book_name=None):
    """
    近 N 天每日复习正确率。
    返回 [(date_str, accuracy_percent_or_None), ...]（旧 -> 新）。
    """
    conn = get_connection()
    cur = conn.cursor()
    sql = """
        SELECT r.review_day, SUM(r.is_right) AS correct, COUNT(*) AS total
        FROM records r JOIN words w ON r.word_id = w.id
        WHERE r.record_type='review'
    """
    params = []
    if book_name:
        sql += " AND w.book_name = ?"
        params.append(book_name)
    sql += " GROUP BY r.review_day ORDER BY r.review_day"
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    by_day = {r['review_day']: (r['correct'], r['total']) for r in rows}
    today = datetime.now().date()
    result = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in by_day:
            c, t = by_day[d]
            result.append((d, round(c / t * 100, 1) if t else None))
        else:
            result.append((d, None))
    return result


def get_forgetting_curve(book_name=None):
    """
    遗忘曲线：按复习间隔 gap_days 分组统计记忆保持率（答对比例）。
    返回 [(gap_days, keep_rate_percent), ...]（按 gap_days 升序）。
    """
    conn = get_connection()
    cur = conn.cursor()
    sql = """
        SELECT r.gap_days, SUM(r.is_right) AS correct, COUNT(*) AS total
        FROM records r JOIN words w ON r.word_id = w.id
        WHERE r.record_type='review' AND r.gap_days IS NOT NULL
    """
    params = []
    if book_name:
        sql += " AND w.book_name = ?"
        params.append(book_name)
    sql += " GROUP BY r.gap_days ORDER BY r.gap_days"
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        if r['total']:
            result.append((r['gap_days'], round(r['correct'] / r['total'] * 100, 1)))
    return result


def get_learn_pending_count(book_name=None):
    """待学习新词数（stage 1~3 未通关三关）。"""
    conn = get_connection()
    cur = conn.cursor()
    if book_name:
        cur.execute("SELECT COUNT(*) FROM words WHERE stage > 0 AND book_name = ?", (book_name,))
    else:
        cur.execute("SELECT COUNT(*) FROM words WHERE stage > 0")
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_review_due_count(book_name=None):
    """待复习单词数（已完成学习且到期）。"""
    conn = get_connection()
    cur = conn.cursor()
    if book_name:
        cur.execute(
            "SELECT COUNT(*) FROM words WHERE stage = 0 AND next_review_day <= date('now') AND book_name = ?",
            (book_name,),
        )
    else:
        cur.execute("SELECT COUNT(*) FROM words WHERE stage = 0 AND next_review_day <= date('now')")
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_today_learned_count(book_name=None):
    """今日新学完（通关三关）的单词数。"""
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    if book_name:
        cur.execute("SELECT COUNT(*) FROM words WHERE completed_day = ? AND book_name = ?", (today, book_name))
    else:
        cur.execute("SELECT COUNT(*) FROM words WHERE completed_day = ?", (today,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_spelling_stats(book_name=None):
    """拼写测试统计：返回 (total, correct)。"""
    conn = get_connection()
    cur = conn.cursor()
    sql = """
        SELECT COUNT(*) AS total, SUM(t.is_correct) AS correct
        FROM test_records t JOIN words w ON t.word_id = w.id
    """
    if book_name:
        sql += " WHERE w.book_name = ?"
        cur.execute(sql, (book_name,))
    else:
        cur.execute(sql)
    row = cur.fetchone()
    conn.close()
    total = row['total'] or 0
    correct = row['correct'] or 0
    return total, correct
