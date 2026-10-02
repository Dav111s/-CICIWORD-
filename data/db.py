# data/db.py
"""SQLite 数据库初始化、迁移与单词/记录/测试记录的增删改查。"""
import sqlite3
import time
from datetime import datetime, timedelta

from paths import db_path
from data.scheduler import get_ebbinghaus_interval


def get_connection():
    """获取数据库连接，并设置行工厂以便按列名访问。"""
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表（words / records / test_records）并执行增量迁移。"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            trans TEXT NOT NULL,
            book_name TEXT,
            create_day TEXT,
            next_review_day TEXT,
            last_review_day TEXT,
            difficulty REAL DEFAULT 0.5,
            stability REAL DEFAULT 1.0,
            lapses INTEGER DEFAULT 0,
            reviews_total INTEGER DEFAULT 0
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER,
            is_right INTEGER NOT NULL,
            review_day TEXT NOT NULL,
            gap_days INTEGER,
            predicted_prob REAL,
            interval_used INTEGER,
            record_type TEXT NOT NULL DEFAULT 'review',
            FOREIGN KEY (word_id) REFERENCES words (id)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS test_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER,
            is_correct INTEGER NOT NULL,
            test_day TEXT NOT NULL,
            FOREIGN KEY (word_id) REFERENCES words (id)
        )
    ''')

    _migrate(conn)

    # 常用索引
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_word ON records(word_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_day ON records(review_day)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_words_book ON words(book_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_words_next ON words(next_review_day)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_test_word ON test_records(word_id)")

    conn.commit()
    conn.close()


def _migrate(conn):
    """增量迁移：为旧库补齐缺失列（不破坏已有数据）。"""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(records)")
    cols = {row[1] for row in cur.fetchall()}
    if 'record_type' not in cols:
        cur.execute("ALTER TABLE records ADD COLUMN record_type TEXT NOT NULL DEFAULT 'review'")
    if 'predicted_prob' not in cols:
        cur.execute("ALTER TABLE records ADD COLUMN predicted_prob REAL")
    if 'interval_used' not in cols:
        cur.execute("ALTER TABLE records ADD COLUMN interval_used INTEGER")

    # words 表：三关学习相关字段（例句 / 当前关卡 / 收藏 / 学完日期）
    cur.execute("PRAGMA table_info(words)")
    wcols = {row[1] for row in cur.fetchall()}
    if 'example' not in wcols:
        cur.execute("ALTER TABLE words ADD COLUMN example TEXT NOT NULL DEFAULT ''")
    if 'stage' not in wcols:
        cur.execute("ALTER TABLE words ADD COLUMN stage INTEGER NOT NULL DEFAULT 1")
    if 'favorite' not in wcols:
        cur.execute("ALTER TABLE words ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
    if 'completed_day' not in wcols:
        cur.execute("ALTER TABLE words ADD COLUMN completed_day TEXT")
    conn.commit()


# ------------------------- 单词查询 -------------------------

def get_due_words(book_name=None):
    """获取今天到期的单词列表（可按词库过滤）。"""
    conn = get_connection()
    cur = conn.cursor()
    if book_name:
        cur.execute(
            "SELECT * FROM words WHERE next_review_day <= date('now') AND book_name = ? ORDER BY id",
            (book_name,),
        )
    else:
        cur.execute("SELECT * FROM words WHERE next_review_day <= date('now') ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_new_words(book_name=None, limit=None):
    """获取未学习的新单词（从未出现在 records 表中的单词）。"""
    conn = get_connection()
    cur = conn.cursor()
    sql = """
        SELECT w.* FROM words w
        LEFT JOIN records r ON w.id = r.word_id
        WHERE r.id IS NULL
    """
    params = []
    if book_name:
        sql += " AND w.book_name = ?"
        params.append(book_name)
    sql += " ORDER BY w.id ASC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_word_by_id(word_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM words WHERE id = ?", (word_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_books():
    """获取所有词本及单词数量。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT book_name, COUNT(*) as cnt, MIN(create_day) as create_day
        FROM words
        GROUP BY book_name
        ORDER BY create_day DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def book_exists(book_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM words WHERE book_name = ?", (book_name,))
    n = cur.fetchone()[0]
    conn.close()
    return n > 0


# ------------------------- 复习/学习记录 -------------------------

def insert_review_record(word_id, is_right, review_day, gap_days,
                         predicted_prob=None, interval_used=None, record_type='review'):
    """插入一条复习/学习记录。record_type: 'review' 或 'learn'。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO records (word_id, is_right, review_day, gap_days, predicted_prob, interval_used, record_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (word_id, 1 if is_right else 0, review_day, gap_days, predicted_prob, interval_used, record_type),
    )
    conn.commit()
    conn.close()


def update_word_after_review(word_id, review_day, next_review_day, stability, difficulty, lapses):
    """更新单词的复习日期、稳定性、难度、遗忘次数。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE words
        SET last_review_day = ?,
            next_review_day = ?,
            stability = ?,
            difficulty = ?,
            lapses = ?,
            reviews_total = reviews_total + 1
        WHERE id = ?
        """,
        (review_day, next_review_day, stability, difficulty, lapses, word_id),
    )
    conn.commit()
    conn.close()


def get_review_records_for_word(word_id, include_learn=True):
    conn = get_connection()
    cur = conn.cursor()
    if include_learn:
        cur.execute("SELECT * FROM records WHERE word_id = ? ORDER BY id", (word_id,))
    else:
        cur.execute("SELECT * FROM records WHERE word_id = ? AND record_type='review' ORDER BY id", (word_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_review_records():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM records ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_record_count(record_type=None):
    conn = get_connection()
    cur = conn.cursor()
    if record_type:
        cur.execute("SELECT COUNT(*) FROM records WHERE record_type = ?", (record_type,))
    else:
        cur.execute("SELECT COUNT(*) FROM records")
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_global_avg_correct():
    """用户全局平均正确率（所有复习记录，无记录返回 0.5）。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT AVG(is_right) FROM records WHERE record_type='review'")
    v = cur.fetchone()[0]
    conn.close()
    return float(v) if v is not None else 0.5


# ------------------------- 拼写测试记录 -------------------------

def insert_test_record(word_id, is_correct, test_day):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO test_records (word_id, is_correct, test_day) VALUES (?, ?, ?)",
        (word_id, 1 if is_correct else 0, test_day),
    )
    conn.commit()
    conn.close()


# ------------------------- 三关学习 / 复习调度 -------------------------

def _update_word_direct(word_id, **fields):
    """按给定字段更新单词（内部辅助，字段名由代码控制）。"""
    if not fields:
        return
    conn = get_connection()
    cur = conn.cursor()
    sets = ', '.join(f"{k} = ?" for k in fields)
    cur.execute(f"UPDATE words SET {sets} WHERE id = ?", list(fields.values()) + [word_id])
    conn.commit()
    conn.close()


def get_learn_queue(book_name=None, limit=None):
    """学习队列：尚未通关三关的单词（stage 1~3）。"""
    conn = get_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM words WHERE stage > 0"
    params = []
    if book_name:
        sql += " AND book_name = ?"
        params.append(book_name)
    sql += " ORDER BY id ASC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_review_queue(book_name=None):
    """复习队列：已完成学习（stage=0）且到期的单词。"""
    conn = get_connection()
    cur = conn.cursor()
    if book_name:
        cur.execute(
            "SELECT * FROM words WHERE stage = 0 AND next_review_day <= date('now') AND book_name = ? "
            "ORDER BY next_review_day ASC, id ASC",
            (book_name,),
        )
    else:
        cur.execute(
            "SELECT * FROM words WHERE stage = 0 AND next_review_day <= date('now') "
            "ORDER BY next_review_day ASC, id ASC"
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_word_streak(word_id):
    """单词当前连续答对次数（从 records 末尾往回数）。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_right FROM records WHERE word_id = ? ORDER BY id DESC", (word_id,))
    streak = 0
    for (is_right,) in cur.fetchall():
        if is_right:
            streak += 1
        else:
            break
    conn.close()
    return streak


def _review_interval(word_id, is_correct, gap_days, streak):
    """
    复习间隔计算：
    - 神经网络可用（.onnx 存在且复习样本 >= MIN_TRAIN_SAMPLES）时，用 NN 预测遗忘概率换算间隔；
    - 否则回退艾宾浩斯阶梯（保持原有行为）。

    返回 (interval, predicted_prob, new_stability, new_difficulty, new_lapses)；
    未用神经网络时后四项为 None。
    """
    from config import MIN_TRAIN_SAMPLES
    try:
        from ai.memory_model import has_model, recommend_interval
        if has_model() and get_record_count('review') >= MIN_TRAIN_SAMPLES:
            rec = recommend_interval(word_id, is_correct, gap_days)
            if rec.get('used_model'):
                return (
                    rec['interval'], rec['forget_prob'],
                    rec['new_stability'], rec['new_difficulty'], rec['new_lapses'],
                )
    except Exception:
        pass
    # 回退：艾宾浩斯阶梯
    if is_correct:
        return get_ebbinghaus_interval(streak + 1), None, None, None, None
    return 1, None, None, None, None


def _learn_completion_interval(word_id, review_day):
    """
    学习通关间隔计算：统一走 memory_model.recommend_interval（is_right=True）。

    - gap_days：基于 word.last_review_day 与本次 review_day 计算，异常兜底为 1；
    - memory_model 导入失败 / 异常时降级回退旧的艾宾浩斯阶梯（保持原行为）；
    - 返回 dict：interval / forget_prob / new_stability / new_difficulty / new_lapses / gap_days。
    """
    word = get_word_by_id(word_id)
    gap_days = 1
    if word and word.get('last_review_day'):
        try:
            gap_days = max(1, (datetime.strptime(review_day, '%Y-%m-%d')
                               - datetime.strptime(word['last_review_day'], '%Y-%m-%d')).days)
        except ValueError:
            gap_days = 1

    try:
        from ai.memory_model import recommend_interval
        rec = recommend_interval(word_id, True, gap_days)  # 学习通关视为「答对」
        return {
            'interval': rec['interval'],
            'forget_prob': rec['forget_prob'],
            'new_stability': rec['new_stability'],
            'new_difficulty': rec['new_difficulty'],
            'new_lapses': rec['new_lapses'],
            'gap_days': gap_days,
        }
    except Exception as e:
        # 降级：memory_model 缺失 / 异常，回退旧的艾宾浩斯阶梯
        print(f"[DEBUG] _learn_completion_interval 降级艾宾浩斯: {e}")
        streak = get_word_streak(word_id)
        return {
            'interval': get_ebbinghaus_interval(streak + 1),
            'forget_prob': None,
            'new_stability': float((word or {}).get('stability') or 1.0),
            'new_difficulty': float((word or {}).get('difficulty') or 0.5),
            'new_lapses': int((word or {}).get('lapses') or 0),
            'gap_days': gap_days,
        }


def submit_answer(word_id, is_correct, mode, review_day=None):
    """
    提交一次作答，执行关卡/间隔调度并写库。

    mode='learn':
      - 答对：stage<3 -> stage+1（继续学习）；stage==3 -> 完成（stage=0，统一走 recommend_interval 排期）。
      - 答错：stage 重置为 1，lapses += 1。
    mode='review':
      - 优先用神经网络预测间隔（模型可用且样本充足时）；
      - 否则回退艾宾浩斯阶梯（答对递增、答错回 1 天），关卡保持 stage=0 不变。

    返回 (updated_word, interval, completed)：
      interval  下次复习间隔天数（学习未完成时为 0）
      completed learn 通关或 review 答对时为 True
    """
    if review_day is None:
        review_day = datetime.now().strftime('%Y-%m-%d')
    today = datetime.strptime(review_day, '%Y-%m-%d')
    word = get_word_by_id(word_id)
    stage = int(word.get('stage') or 1)
    streak = get_word_streak(word_id)
    is_right = 1 if is_correct else 0

    if mode == 'learn':
        if is_correct:
            if stage >= 3:
                # 学习通关：统一走 recommend_interval（含 forget_prob / SM-2 回退 + 记忆状态更新）
                rec = _learn_completion_interval(word_id, review_day)
                interval = rec['interval']
                next_day = (today + timedelta(days=interval)).strftime('%Y-%m-%d')
                # 调试埋点：确认间隔与记忆状态已区分
                print(f"[DEBUG] learn通关 wid={word_id} interval={interval} forget_prob={rec['forget_prob']} "
                      f"stability={rec['new_stability']} difficulty={rec['new_difficulty']} lapses={rec['new_lapses']}")
                _update_word_direct(
                    word_id, stage=0, last_review_day=review_day,
                    next_review_day=next_day, completed_day=review_day,
                    stability=rec['new_stability'], difficulty=rec['new_difficulty'], lapses=rec['new_lapses'],
                )
                insert_review_record(word_id, is_right, review_day, rec['gap_days'], rec['forget_prob'], interval, 'learn')
                return get_word_by_id(word_id), interval, True
            _update_word_direct(word_id, stage=stage + 1)
            insert_review_record(word_id, is_right, review_day, 0, None, None, 'learn')
            return get_word_by_id(word_id), 0, False
        # 答错：stage 重置为 1，并累加 lapses（学习阶段就落库记忆状态）
        _update_word_direct(word_id, stage=1, lapses=int(word.get('lapses') or 0) + 1)
        insert_review_record(word_id, is_right, review_day, 0, None, None, 'learn')
        return get_word_by_id(word_id), 0, False

    # review 模式：优先神经网络，样本不足/无模型时回退艾宾浩斯阶梯
    gap_days = 1
    if word.get('last_review_day'):
        try:
            gap_days = max(1, (today - datetime.strptime(word['last_review_day'], '%Y-%m-%d')).days)
        except ValueError:
            gap_days = 1

    interval, prob, ns, nd, nl = _review_interval(word_id, is_correct, gap_days, streak)
    next_day = (today + timedelta(days=interval)).strftime('%Y-%m-%d')
    _update_word_direct(word_id, last_review_day=review_day, next_review_day=next_day)
    if ns is not None:
        _update_word_direct(word_id, stability=ns, difficulty=nd, lapses=nl)
    insert_review_record(word_id, is_right, review_day, gap_days, prob, interval, 'review')
    return get_word_by_id(word_id), interval, bool(is_correct)


def submit_review_three_tier(word_id, feedback, word_freq=None):
    """
    三档复习提交：记住/模糊/忘记（SRS 记忆概率 + 难度系数决定间隔，替换艾宾浩斯）。

    feedback: srs.ReviewFeedback 或 'remember'/'hazy'/'forget'。
    返回 (updated_word, interval_days, completed)。
    """
    import srs as srs_mod

    dbp = str(db_path())
    word = get_word_by_id(word_id)
    if word is None:
        return None, 0, False

    fb = feedback if isinstance(feedback, srs_mod.ReviewFeedback) else srs_mod.ReviewFeedback(str(feedback))
    freq = float(word_freq) if word_freq is not None else 0.5

    now = int(time.time())
    srs_mod.init_srs_schema(dbp)  # 确保 srs 表存在
    record = srs_mod.load_srs_record(str(word_id), dbp) or srs_mod.SrsRecord(
        record_id=str(word_id), word=word['word'],
    )
    updated = srs_mod.process_review_feedback(record, fb, freq, now_ts=now, db_path=dbp, use_neural=False)

    review_day = datetime.fromtimestamp(now).strftime('%Y-%m-%d')
    next_day = datetime.fromtimestamp(updated.next_review_ts).strftime('%Y-%m-%d')
    interval_days = max(1, int(round((updated.next_review_ts - now) / 86400)))

    gap_days = 1
    if word.get('last_review_day'):
        try:
            gap_days = max(1, (datetime.strptime(review_day, '%Y-%m-%d') - datetime.strptime(word['last_review_day'], '%Y-%m-%d')).days)
        except ValueError:
            gap_days = 1

    is_right = 1 if fb == srs_mod.ReviewFeedback.REMEMBER else 0
    _update_word_direct(word_id, last_review_day=review_day, next_review_day=next_day)
    insert_review_record(word_id, is_right, review_day, gap_days, updated.memory_prob, interval_days, 'review')
    return get_word_by_id(word_id), interval_days, True


def set_word_favorite(word_id, favorite):
    _update_word_direct(word_id, favorite=1 if favorite else 0)


def set_word_example(word_id, example):
    _update_word_direct(word_id, example=(example or '').strip())


def mark_word_known(word_id):
    """标记熟词：直接视为已学（stage=0），30 天后复习。"""
    today = datetime.now().strftime('%Y-%m-%d')
    next_day = (datetime.strptime(today, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')
    _update_word_direct(word_id, stage=0, last_review_day=today, next_review_day=next_day, completed_day=today)
    insert_review_record(word_id, 1, today, 0, None, 30, 'learn')
    return get_word_by_id(word_id)


def get_distractors(word_id, book_name=None, count=3):
    """随机取 count 个其它单词的释义，作为选择题干扰项。"""
    conn = get_connection()
    cur = conn.cursor()
    if book_name:
        cur.execute(
            "SELECT trans FROM words WHERE id != ? AND book_name = ? ORDER BY RANDOM() LIMIT ?",
            (word_id, book_name, count),
        )
    else:
        cur.execute(
            "SELECT trans FROM words WHERE id != ? ORDER BY RANDOM() LIMIT ?",
            (word_id, count),
        )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_words_by_book(book_name):
    """读取指定词本的全部单词（word / trans / example），供词本详情浏览。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, word, trans, example FROM words WHERE book_name = ? ORDER BY id",
        (book_name,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_favorite_words(book_name=None):
    """读取已收藏的单词（复用 favorite 字段，不新增表/字段）。"""
    conn = get_connection()
    cur = conn.cursor()
    if book_name:
        cur.execute(
            "SELECT id, word, trans, example FROM words WHERE favorite = 1 AND book_name = ? ORDER BY id",
            (book_name,),
        )
    else:
        cur.execute("SELECT id, word, trans, example FROM words WHERE favorite = 1 ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]
