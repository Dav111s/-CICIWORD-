#!/usr/bin/env python3
"""
⚠️ 警告：本脚本仅【本地开发调试】专用。
伪造模拟数据生成的 dummy 模型，权重没有真实业务效果，仅用来跑通 used_model=True 完整链路，
【严禁】随正式 App 打包分发。

多输出头模式（方案A）：
- forget_logits(1)   -> 推理端 sigmoid 得 forget_prob ∈ [0,1]
- stability(1)       -> 模型内 Softplus，推理端 clip 0.5~30
- difficulty(1)      -> 模型内 Sigmoid，推理端 clip 0.1~0.9

用法：
    python scripts/generate_dummy_test_model.py

产物（直接写入项目 ai/ 目录）：
    ai/memory_model.onnx     -> 3 个输出 forget_logits / stability / difficulty
    ai/memory_model.pth      -> PyTorch 权重
    ai/train_meta.json       -> mode=MODE_A_STABLE_MULTI、output_dim=3、mean=0、std=1
"""
import json
import os
import random
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta

import numpy as np

# 项目根目录（scripts/ 的上一级），保证能导入项目模块
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 依赖检查（torch 仅训练需要）
try:
    import torch  # noqa: F401
    import torch.nn as nn  # noqa: F401
except ImportError:
    print("[dummy] 缺少 torch，无法训练。请先执行：pip install torch")
    sys.exit(1)

# 1. 隔离临时数据目录：伪造数据只写进临时库，绝不污染真实 vocab.db
TMP_DIR = tempfile.mkdtemp(prefix="dummy_model_")
os.environ["WORD_APP_DATA_DIR"] = TMP_DIR

from data.db import init_db, get_connection  # noqa: E402
from ai import memory_model  # noqa: E402


def build_dummy_data(num_words: int = 200, records_per_word: int = 6) -> None:
    """构造模拟单词与复习记录，覆盖不同 stability / difficulty / lapses / gap / 正误标签。"""
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.now()
    for i in range(num_words):
        # target stability 覆盖 0.5~30，target difficulty 覆盖 0.1~0.9，均变化（不要固定值）
        stability = round(random.uniform(0.5, 30.0), 3)
        difficulty = round(random.uniform(0.1, 0.9), 3)
        lapses = random.randint(0, 6)
        cur.execute(
            "INSERT INTO words (word, trans, book_name, create_day, next_review_day, "
            "difficulty, stability, lapses, stage) "
            "VALUES (?, ?, 'dummy', date('now'), date('now'), ?, ?, ?, 0)",
            (f"dummy{i}", f"模拟词{i}", difficulty, stability, lapses),
        )
        wid = cur.lastrowid
        last_day = today
        for j in range(records_per_word):
            is_right = 1 if (j + i) % 3 != 0 else 0          # 约 2/3 答对，1/3 答错
            gap = random.choice([1, 2, 3, 4, 7, 15, 30])
            review_day = (last_day - timedelta(days=gap)).strftime('%Y-%m-%d')
            cur.execute(
                "INSERT INTO records (word_id, is_right, review_day, gap_days, record_type) "
                "VALUES (?, ?, ?, ?, 'review')",
                (wid, is_right, review_day, gap),
            )
            last_day = datetime.strptime(review_day, '%Y-%m-%d')
    conn.commit()
    conn.close()
    print(f"[dummy] 已构造 {num_words} 词 / {num_words * records_per_word} 条模拟复习记录")


def build_multi_training_data():
    """构造多输出头训练数据：X + (forget_y, stability_y, difficulty_y)。

    - forget_y：0/1（is_right -> 0 记得，else 1 遗忘）
    - stability_y：目标 stability（词库中变化的 stability）
    - difficulty_y：目标 difficulty（词库中变化的 difficulty）
    """
    recs = memory_model.db.get_all_review_records()
    if len(recs) < memory_model.MIN_TRAIN_SAMPLES:
        return None

    X, y_forget, y_stab, y_diff = [], [], [], []
    for r in recs:
        wid = r['word_id']
        f = memory_model.extract_features(wid)
        if f is None:
            continue
        word = memory_model.db.get_word_by_id(wid)
        X.append(f)
        y_forget.append(0.0 if r['is_right'] else 1.0)
        y_stab.append(float(word['stability']))
        y_diff.append(float(word['difficulty']))

    if len(X) < memory_model.MIN_TRAIN_SAMPLES:
        return None

    return (
        np.array(X, dtype=np.float32),
        np.array(y_forget, dtype=np.float32).reshape(-1, 1),
        np.array(y_stab, dtype=np.float32).reshape(-1, 1),
        np.array(y_diff, dtype=np.float32).reshape(-1, 1),
    )


class LocalForgettingNet(nn.Module):
    """多输出头：Linear(8,32)→ReLU→Linear(32,16)→ReLU 共享层 + 三个头。

    - head_forget    Linear(16,1)                  -> forget_logits（无激活，推理端 sigmoid）
    - head_stability Linear(16,1)+Softplus         -> stability（>0，推理端 clip 0.5~30）
    - head_difficulty Linear(16,1)+Sigmoid         -> difficulty（0~1，推理端 clip 0.1~0.9）
    """

    def __init__(self):
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(8, 32), nn.ReLU(),
            nn.Linear(32, 16), nn.ReLU(),
        )
        self.head_forget = nn.Linear(16, 1)                      # 原始 logits
        self.head_stability = nn.Sequential(nn.Linear(16, 1), nn.Softplus())  # softplus
        self.head_difficulty = nn.Sequential(nn.Linear(16, 1), nn.Sigmoid())  # sigmoid

    def forward(self, x):
        h = self.shared(x)
        forget = self.head_forget(h)          # logits
        stability = self.head_stability(h)    # softplus 输出
        difficulty = self.head_difficulty(h)  # sigmoid 输出
        return forget, stability, difficulty


def main() -> None:
    assert memory_model.MODE_A_STABLE, "[dummy] 仅支持 MODE_A_STABLE 模式"

    init_db()
    build_dummy_data()

    data = build_multi_training_data()
    if data is None:
        print("[dummy] 训练数据不足")
        shutil.rmtree(TMP_DIR, ignore_errors=True)
        sys.exit(1)
    X, y_forget, y_stab, y_diff = data

    import torch
    import torch.nn as nn

    model = LocalForgettingNet()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    bce_logits = nn.BCEWithLogitsLoss()  # forget logits -> sigmoid+BCE
    mse = nn.MSELoss()                   # stability / difficulty 回归

    Xt = torch.from_numpy(X)
    yf = torch.from_numpy(y_forget)
    ys = torch.from_numpy(y_stab)
    yd = torch.from_numpy(y_diff)

    model.train()
    for _epoch in range(300):
        opt.zero_grad()
        forget_logits, stab_pred, diff_pred = model(Xt)
        loss = bce_logits(forget_logits, yf) + mse(stab_pred, ys) + mse(diff_pred, yd)
        loss.backward()
        opt.step()
    model.eval()

    # 输出目录
    dst_ai = os.path.join(PROJECT_ROOT, "ai")
    os.makedirs(dst_ai, exist_ok=True)
    dst_pth = os.path.join(dst_ai, "memory_model.pth")
    dst_onnx = os.path.join(dst_ai, "memory_model.onnx")
    dst_meta = os.path.join(dst_ai, "train_meta.json")

    # 保存 pth
    torch.save(model.state_dict(), dst_pth)
    print(f"[dummy] 已输出 {dst_pth}")

    # 导出 onnx：3 输出 forget_logits / stability / difficulty，dynamo=False 权重内嵌
    import contextlib
    import io
    dummy = torch.zeros(1, 8, dtype=torch.float32)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        torch.onnx.export(
            model, dummy, dst_onnx,
            input_names=['features'],
            output_names=['forget_logits', 'stability', 'difficulty'],
            opset_version=13,
            dynamo=False,
        )
    print(f"[dummy] 已输出 {dst_onnx}")

    # train_meta：mode=MODE_A_STABLE_MULTI，输出维度 3，mean=0 / std=1
    meta = {
        'last_train_ts': time.time(),
        'num_samples': int(len(X)),
        'feature_mean': [0.0] * 8,
        'feature_std': [1.0] * 8,
        'mode': 'MODE_A_STABLE_MULTI',
        'output_dim': 3,
    }
    with open(dst_meta, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    print(f"[dummy] 已输出 {dst_meta}")

    # 清理临时目录
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    print("[dummy] 完成。dummy 多输出头模型无真实业务效果，仅用于跑通 used_model=True 链路")


if __name__ == "__main__":
    main()
