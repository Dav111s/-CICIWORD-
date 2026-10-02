# config.py
"""全局配置常量与 settings.json 读写。"""
import json
import os
from datetime import datetime

from paths import settings_path

# 默认复习间隔（冷启动）
DEFAULT_INTERVALS = [1, 3, 7, 15, 30]

# 遗忘概率 -> 间隔（旧规则，保留兼容）
FORGET_PROB_INTERVAL_MAP = [
    (0.75, 1),
    (0.50, 2),
    (0.25, 4),
    (0.0, 7),
]

# 训练最少样本数（复习记录）
MIN_TRAIN_SAMPLES = 50

# 距离上次训练超过该秒数才允许增量训练
RETRAIN_INTERVAL_SECONDS = 10 * 60

# 学习模式首次复习间隔（天）
LEARN_INTERVAL_KNOWN = 3      # 认识 -> 3 天后复习
LEARN_INTERVAL_UNKNOWN = 1    # 不认识 -> 1 天后复习

# 设置默认值
DEFAULT_SETTINGS = {
    "current_book": None,           # 当前词库名称
    "study_group_size": 10,         # 每组学习词数（5~50）
    "spelling_test_enabled": False, # 学习后是否开启拼写测试
    "daily_new_word_limit": 0,      # 预留：每日新词上限（0=不限）
    "bg_gradient": 0,               # 首页背景渐变索引（0/1/2）
    "study_duration": {},           # 今日学习时长 {"date": "YYYY-MM-DD", "seconds": N}
}


def load_settings() -> dict:
    """从 settings.json 读取配置并合并默认值；文件缺失/损坏时返回默认。"""
    settings = dict(DEFAULT_SETTINGS)
    path = settings_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                settings.update(loaded)
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(settings: dict):
    """保存配置到 settings.json。"""
    with open(settings_path(), 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


def get_setting(key, default=None):
    if default is None:
        default = DEFAULT_SETTINGS.get(key)
    return load_settings().get(key, default)


def set_setting(key, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)


def get_current_book():
    """获取当前词库名称，未设置返回 None。"""
    return get_setting('current_book', None)


def set_current_book(book_name):
    set_setting('current_book', book_name)


def get_study_group_size() -> int:
    try:
        return max(5, min(50, int(get_setting('study_group_size', 10))))
    except (TypeError, ValueError):
        return 10


def set_study_group_size(n: int):
    set_setting('study_group_size', max(5, min(50, int(n))))


def is_spelling_test_enabled() -> bool:
    return bool(get_setting('spelling_test_enabled', False))


def set_spelling_test_enabled(enabled: bool):
    set_setting('spelling_test_enabled', bool(enabled))


def get_bg_gradient() -> int:
    """当前主题索引（0~5，共 6 种多巴胺渐变主题）。"""
    try:
        return max(0, min(5, int(get_setting('bg_gradient', 0))))
    except (TypeError, ValueError):
        return 0


def set_bg_gradient(index: int):
    set_setting('bg_gradient', max(0, min(5, int(index))))


def add_study_duration(seconds: int):
    """累加今日学习时长（秒），按天隔离。"""
    if seconds <= 0:
        return
    settings = load_settings()
    today = datetime.now().strftime('%Y-%m-%d')
    dur = settings.get('study_duration')
    if not isinstance(dur, dict) or dur.get('date') != today:
        dur = {'date': today, 'seconds': 0}
    dur['seconds'] = int(dur.get('seconds', 0) or 0) + int(seconds)
    settings['study_duration'] = dur
    save_settings(settings)


def get_today_study_duration() -> int:
    """今日已累计学习时长（秒）。"""
    dur = get_setting('study_duration', {})
    if isinstance(dur, dict) and dur.get('date') == datetime.now().strftime('%Y-%m-%d'):
        return int(dur.get('seconds', 0) or 0)
    return 0
