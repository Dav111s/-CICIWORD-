# paths.py
"""跨平台路径管理。

- 桌面端：数据库 / settings.json / 模型文件 默认存放在项目根目录
  （与旧版 vocab.db、settings.json 兼容，不破坏已有数据）。
- 安卓端（Flet 打包）：通过环境变量 WORD_APP_DATA_DIR 注入应用私有可写目录；
  未注入时回退到项目根目录。
- 内置词本始终打包在包内 data/builtin，随应用只读分发，保证离线可用。
"""
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent


def get_data_dir() -> Path:
    """可写数据目录（数据库、settings.json、模型文件）。"""
    env = os.environ.get("WORD_APP_DATA_DIR")
    if env:
        return Path(env)
    return _PROJECT_ROOT


def ensure_data_dir() -> Path:
    d = get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return get_data_dir() / "vocab.db"


def settings_path() -> Path:
    return get_data_dir() / "settings.json"


def model_dir() -> Path:
    d = get_data_dir() / "ai"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_pth_path() -> Path:
    return model_dir() / "memory_model.pth"


def model_onnx_path() -> Path:
    return model_dir() / "memory_model.onnx"


def train_meta_path() -> Path:
    return model_dir() / "train_meta.json"


def builtin_csv_dir() -> Path:
    """内置词本目录（打包进应用，只读）。"""
    return _PROJECT_ROOT / "data" / "builtin"
