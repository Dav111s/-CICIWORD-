# ai/memory_model.py
"""
遗忘预测神经网络：PyTorch 训练 + ONNX Runtime 推理。

模型结构：
    输入层  8 个特征
    共享隐藏层 32 -> 16 (ReLU)
    输出（按运行模式）：
        MODE_A_STABLE   1 输出：遗忘概率 prob (Sigmoid)
        MODE_B_EXPERIMENT 3 输出：遗忘概率 prob(Sigmoid)、
                                  stability 增量(Sigmoid)、difficulty 增量(Sigmoid)

特征（8 维，见 FEATURE_NAMES）：
    1. 历史复习总次数（log1p）
    2. 历史平均正确率
    3. 最近一次复习间隔天数（log1p）
    4. 距离上次复习过去的天数（log1p）
    5. 连续答对次数（log1p）
    6. 连续答错次数（log1p）
    7. 单词难度（0~1）
    8. 用户全局平均正确率（0~1）

训练数据说明（时间泄露折中，见 build_training_data）：
    records 表未保存每条记录“当时”的特征快照，训练样本特征用该单词“当前”状态近似；
    对复习记录数很少的单词样本做降权，缓解近似偏差。未来演进方案见文件底部注释。

推理：优先 ONNX Runtime（CPU）；模型缺失 / 样本不足 / 输入非法 / 推理异常时
    回退到简化 SM-2 规则。torch 仅训练时按需导入，移动端可只装 onnxruntime。

日志：不硬编码 print，通过 set_log_callback() 注入日志处理器。
"""
import json
import math
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from config import MIN_TRAIN_SAMPLES, RETRAIN_INTERVAL_SECONDS
from data import db
from paths import model_pth_path, model_onnx_path, train_meta_path

# ========== 全局配置开关 ==========
# 是否开启后台自动训练模型；【正式打包发布 APP 务必设置 = False】
ENABLE_BACKGROUND_TRAIN: bool = True
# 【仅开发调试用】强制绕过review样本数量门槛，只要有onnx模型就启用AI推理；正式打包务必=False
DEV_FORCE_SKIP_SAMPLE_THRESHOLD: bool = True

# ============================ 运行模式开关 ============================
# MODE_A_STABLE（默认开启）：网络只预测遗忘概率，stability/difficulty/lapses 用手写规则更新。
# MODE_B_EXPERIMENT：网络同时预测遗忘概率 + stability 增量 + difficulty 增量，替换手写规则。
# 注意：切换模式后需重新训练（模型输出维度不同，旧 onnx 不兼容）。
MODE_A_STABLE: bool = True
MODE_B_EXPERIMENT: bool = (not MODE_A_STABLE)

FEATURE_NAMES: List[str] = [
    'history_count', 'avg_correct', 'last_gap_days',
    'days_since_last_review', 'streak_correct', 'streak_wrong',
    'difficulty', 'global_avg_correct',
]

INPUT_DIM: int = 8
# 输出维度：MODE_A=1（遗忘概率），MODE_B=3（遗忘概率、stability 增量、difficulty 增量）
OUTPUT_DIM: int = 1 if MODE_A_STABLE else 3

# 各特征合法值域（用于输入校验与裁剪），防止脏数据炸 onnx 推理
FEATURE_BOUNDS: List[Tuple[float, float]] = [
    (0.0, 12.0),   # history_count
    (0.0, 1.0),    # avg_correct
    (0.0, 6.5),    # last_gap_days（log1p(365)≈5.9）
    (0.0, 6.5),    # days_since_last_review
    (0.0, 12.0),   # streak_correct
    (0.0, 12.0),   # streak_wrong
    (0.0, 1.0),    # difficulty
    (0.0, 1.0),    # global_avg_correct
]

# 特征缓存：TTL（秒）+ LRU 容量，降低高频 extract_features 的数据库压力
FEATURE_CACHE_TTL: float = 30.0
FEATURE_CACHE_CAPACITY: int = 512

# 时间泄露降权：单词复习记录数 < 该阈值时线性降低该样本权重
MIN_RECORDS_FOR_FULL_WEIGHT: int = 5

# ============================ 日志钩子 ============================
# 日志回调类型：上层可注入文件日志等处理器，替代 print。
LogFn = Callable[[str], None]

_log_fn: LogFn = lambda msg: None


def set_log_callback(fn: Optional[LogFn]) -> None:
    """上层注入日志处理器（如写文件）；传 None 恢复默认静默。"""
    global _log_fn
    _log_fn = fn or (lambda msg: None)


def _log(msg: str) -> None:
    """统一日志出口，绝不抛异常。"""
    try:
        _log_fn(msg)
    except Exception:
        pass


# ============================ 特征工程 ============================

# 特征 LRU-TTL 缓存：word_id -> (expire_ts, features)
_feature_cache: "OrderedDict[int, Tuple[float, np.ndarray]]" = OrderedDict()
_feature_cache_lock = threading.Lock()


def _log1p(x) -> float:
    return math.log1p(max(0.0, float(x)))


def _clamp_features(feats) -> np.ndarray:
    """把特征裁剪到合法值域，并替换非有限值为 0。"""
    arr = np.asarray(feats, dtype=np.float32).reshape(INPUT_DIM).copy()
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    for i, (lo, hi) in enumerate(FEATURE_BOUNDS):
        arr[i] = float(max(lo, min(hi, float(arr[i]))))
    return arr


def extract_features(word_id) -> Optional[np.ndarray]:
    """
    提取单词当前状态的特征向量（8 维，已归一化并裁剪到合法值域）。

    - 带 TTL + LRU 内存缓存，缓解复习量大时的数据库压力；
    - 计数类特征取 log1p 压缩，比率类特征保持 [0,1]；
    - 无单词或无法计算时返回 None。
    """
    now = time.time()
    with _feature_cache_lock:
        if word_id in _feature_cache:
            expire_ts, feats = _feature_cache[word_id]
            if now < expire_ts:
                _feature_cache.move_to_end(word_id)  # LRU：命中移到末尾
                return feats
            del _feature_cache[word_id]

    word = db.get_word_by_id(word_id)
    if word is None:
        return None

    recs = db.get_review_records_for_word(word_id, include_learn=True)
    n = len(recs)
    avg_correct = (sum(1 for r in recs if r['is_right']) / n) if n else 0.5

    last_gap = 0
    if recs:
        last_gap = recs[-1]['gap_days'] if recs[-1]['gap_days'] is not None else 0

    days_since = 0
    if word.get('last_review_day'):
        try:
            last = datetime.strptime(word['last_review_day'], '%Y-%m-%d').date()
            days_since = max(0, (datetime.now().date() - last).days)
        except (ValueError, TypeError):
            days_since = 0

    streak_correct = 0
    for r in reversed(recs):
        if r['is_right']:
            streak_correct += 1
        else:
            break
    streak_wrong = 0
    for r in reversed(recs):
        if not r['is_right']:
            streak_wrong += 1
        else:
            break

    difficulty = float(word.get('difficulty') or 0.5)
    global_acc = db.get_global_avg_correct()

    features = _clamp_features([
        _log1p(n),               # 1. 历史复习总次数
        float(avg_correct),      # 2. 平均正确率
        _log1p(last_gap),        # 3. 最近间隔天数
        _log1p(days_since),      # 4. 距上次复习天数
        _log1p(streak_correct),  # 5. 连续答对
        _log1p(streak_wrong),    # 6. 连续答错
        max(0.0, min(1.0, difficulty)),  # 7. 难度
        float(global_acc),       # 8. 全局正确率
    ])

    with _feature_cache_lock:
        _feature_cache[word_id] = (now + FEATURE_CACHE_TTL, features)
        if len(_feature_cache) > FEATURE_CACHE_CAPACITY:
            _feature_cache.popitem(last=False)  # 淘汰最久未用
    return features


def _validate_features(feats) -> bool:
    """输入合法性校验：形状正确 + 全有限值。"""
    if feats is None:
        return False
    arr = np.asarray(feats, dtype=np.float32).reshape(-1)
    if arr.shape[0] != INPUT_DIM:
        return False
    if not np.isfinite(arr).all():
        return False
    return True


# ============================ 神经网络（PyTorch） ============================

def build_model():
    """按运行模式构建模型；torch 仅在此处按需导入。"""
    import torch
    import torch.nn as nn

    class ForgettingNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.shared = nn.Sequential(
                nn.Linear(INPUT_DIM, 32),
                nn.ReLU(),
                nn.Linear(32, 16),
                nn.ReLU(),
            )
            if MODE_A_STABLE:
                self.head_prob = nn.Sequential(nn.Linear(16, 1), nn.Sigmoid())
            else:
                self.head_prob = nn.Sequential(nn.Linear(16, 1), nn.Sigmoid())
                self.head_stab = nn.Sequential(nn.Linear(16, 1), nn.Sigmoid())
                self.head_diff = nn.Sequential(nn.Linear(16, 1), nn.Sigmoid())

        def forward(self, x):
            h = self.shared(x)
            if MODE_A_STABLE:
                return self.head_prob(h)
            return torch.cat([self.head_prob(h), self.head_stab(h), self.head_diff(h)], dim=1)

    return ForgettingNet()


def build_training_data():
    """
    从 records 构造训练样本 (X, y, w)。

    - 时间泄露折中：records 未保存当时特征快照，用“当前特征”近似当时状态；
      对复习记录数很少的单词样本线性降权（MIN_RECORDS_FOR_FULL_WEIGHT 以下）。
    - 样本清洗：过滤 NaN / inf；裁剪越界特征后再过滤一次。
    - MODE_A 标签：[遗忘概率]；MODE_B 标签：[遗忘概率, stability增量, difficulty增量]。
    - 记录数 < MIN_TRAIN_SAMPLES 时返回 (None, None, None)。
    """
    recs = db.get_all_review_records()
    if len(recs) < MIN_TRAIN_SAMPLES:
        return None, None, None

    # 统计每个单词的记录数，用于时间泄露降权
    word_rec_count: Dict[int, int] = {}
    for r in recs:
        wid = r['word_id']
        word_rec_count[wid] = word_rec_count.get(wid, 0) + 1

    feat_cache: Dict[int, Optional[np.ndarray]] = {}
    X: List[np.ndarray] = []
    y: List[List[float]] = []
    w: List[float] = []

    for r in recs:
        wid = r['word_id']
        if wid not in feat_cache:
            feat_cache[wid] = extract_features(wid)
        f = feat_cache[wid]
        if f is None:
            continue
        if not np.isfinite(f).all():  # 脏样本直接丢弃
            continue

        X.append(f)
        if MODE_A_STABLE:
            y.append([0.0 if r['is_right'] else 1.0])
        else:
            # MODE_B 目标：遗忘概率、stability 增量(答对增/答错减)、difficulty 增量
            y.append([
                0.0 if r['is_right'] else 1.0,
                0.3 if r['is_right'] else -0.4,   # stability 增量
                0.0 if r['is_right'] else 0.1,     # difficulty 增量
            ])

        # 时间泄露降权：记录数少的单词，当前特征对“当时”的近似偏差更大
        n = word_rec_count.get(wid, 0)
        weight = min(1.0, n / float(MIN_RECORDS_FOR_FULL_WEIGHT))
        w.append(max(0.1, weight))

    if len(X) < MIN_TRAIN_SAMPLES:
        return None, None, None

    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.float32)
    w = np.array(w, dtype=np.float32).reshape(-1, 1)

    # 裁剪越界 + 再次过滤非有限样本
    X = np.stack([_clamp_features(row) for row in X])
    mask = np.isfinite(X).all(axis=1)
    X, y, w = X[mask], y[mask], w[mask]
    if len(X) < MIN_TRAIN_SAMPLES:
        return None, None, None
    return X, y, w


def _save_train_meta(num_samples: int, feature_mean: np.ndarray, feature_std: np.ndarray) -> None:
    """保存训练元数据：样本数、时间戳、特征 mean/std（训练/推理统一标准化）。"""
    meta = {
        'last_train_ts': time.time(),
        'num_samples': int(num_samples),
        'feature_mean': np.asarray(feature_mean, dtype=np.float32).reshape(-1).tolist(),
        'feature_std': np.asarray(feature_std, dtype=np.float32).reshape(-1).tolist(),
        'mode': 'MODE_A_STABLE' if MODE_A_STABLE else 'MODE_B_EXPERIMENT',
        'output_dim': OUTPUT_DIM,
    }
    try:
        with open(train_meta_path(), 'w', encoding='utf-8') as f:
            json.dump(meta, f)
    except OSError as e:
        _log(f"[memory_model] 保存 train_meta 失败: {e}")


def _load_meta() -> Dict:
    """读取训练元数据；缺失/损坏返回空 dict。"""
    try:
        with open(train_meta_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def train_model(force: bool = False) -> bool:
    """
    训练模型：8:2 划分、加权 BCE/MSE、early-stop、特征标准化、pth+onnx 双输出。

    - 训练成功后保存 .pth 与 .onnx，并写入 feature_mean/std 到 train_meta；
    - Windows GBK 控制台下 torch.onnx.export 会打印 emoji 日志导致 UnicodeEncodeError，
      故重定向 stdout/stderr。
    """
    if not force and not should_train():
        return False

    X, y, w = build_training_data()
    if X is None or len(X) < MIN_TRAIN_SAMPLES:
        return False

    import torch
    import torch.nn as nn

    # 8:2 训练/验证集切分
    n = len(X)
    idx = np.random.permutation(n)
    split = max(1, int(n * 0.8))
    tr_idx, va_idx = idx[:split], idx[split:]
    Xtr, ytr, wtr = X[tr_idx], y[tr_idx], w[tr_idx]
    Xva, yva = X[va_idx], y[va_idx]

    # 特征标准化（用训练集统计量，推理阶段复用）
    mean = Xtr.mean(axis=0, keepdims=True)
    std = Xtr.std(axis=0, keepdims=True) + 1e-6
    Xtr_n = (Xtr - mean) / std
    Xva_n = (Xva - mean) / std

    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    bce = nn.BCELoss()
    mse = nn.MSELoss()

    Xt = torch.from_numpy(Xtr_n)
    yt = torch.from_numpy(ytr)
    wt = torch.from_numpy(wtr)
    Xv = torch.from_numpy(Xva_n)
    yv = torch.from_numpy(yva)

    def _loss(pred, target, weight):
        # 第 0 列（遗忘概率）用加权 BCE；其余列（增量）用加权 MSE
        p0, t0 = pred[:, :1], target[:, :1]
        loss = (bce(p0, t0) * weight).mean()
        if pred.shape[1] > 1:
            loss = loss + (mse(pred[:, 1:], target[:, 1:]) * weight).mean()
        return loss

    best_vloss = float('inf')
    best_state = None
    patience = 10
    no_improve = 0

    for _epoch in range(200):
        model.train()
        opt.zero_grad()
        pred = model(Xt)
        loss = _loss(pred, yt, wt)
        loss.backward()
        opt.step()

        model.eval()
        with torch.no_grad():
            vloss = float(_loss(model(Xv), yv, torch.ones((yv.shape[0], 1))))
        if vloss < best_vloss - 1e-4:
            best_vloss = vloss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()

    # 保存 .pth
    try:
        torch.save(model.state_dict(), str(model_pth_path()))
    except OSError as e:
        _log(f"[memory_model] 保存 pth 失败: {e}")
        return False

    # 导出 .onnx（重定向 stdout/stderr 规避 GBK 编码报错）
    import contextlib
    import io
    output_names = ['prob'] if OUTPUT_DIM == 1 else ['prob', 'stab_delta', 'diff_delta']
    try:
        dummy = torch.zeros(1, INPUT_DIM, dtype=torch.float32)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            torch.onnx.export(
                model, dummy, str(model_onnx_path()),
                input_names=['features'], output_names=output_names,
                opset_version=13,
                dynamo=False,  # 使用旧版导出器：权重内嵌、不产生外部 .onnx.data 文件
            )
    except Exception as e:
        _log(f"[memory_model] 导出 onnx 失败: {e}")
        return False

    _save_train_meta(len(X), mean, std)
    reset_session()
    _log(f"[memory_model] 训练完成: {len(X)} 样本")
    return True


def train_async(force: bool = False) -> Optional[threading.Thread]:
    """后台线程增量训练，避免阻塞界面。

    - ENABLE_BACKGROUND_TRAIN=False 时（正式发布），非 force 调用直接跳过，不在用户设备上自动训练。
    """
    if not ENABLE_BACKGROUND_TRAIN and not force:
        _log("[memory_model] 后台自动训练已关闭(ENABLE_BACKGROUND_TRAIN=False)，跳过")
        return None

    def _run():
        try:
            train_model(force=force)
        except Exception as e:
            _log(f"[memory_model] 后台训练异常: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ============================ ONNX Runtime 推理 ============================

_session = None
_session_path: Optional[str] = None
_session_lock = threading.Lock()


def _destroy_session_locked() -> None:
    """销毁当前 ONNX 会话（需持有 _session_lock）。"""
    global _session, _session_path
    if _session is not None:
        try:
            del _session
        except Exception:
            pass
    _session = None
    _session_path = None


def _get_session():
    """获取 ONNX 会话（带锁）；加载失败时销毁并重试一次。"""
    global _session, _session_path
    onnx_path = str(model_onnx_path())
    with _session_lock:
        if _session is not None and _session_path == onnx_path:
            return _session
        if not os.path.exists(onnx_path):
            return None
        import onnxruntime as ort
        for attempt in range(2):
            try:
                _session = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
                _session_path = onnx_path
                return _session
            except Exception as e:
                _log(f"[memory_model] onnx 会话加载失败(第{attempt + 1}次): {e}")
                _destroy_session_locked()
        return None


def reset_session() -> None:
    """重置 ONNX 会话（训练后 / 推理异常后调用）。"""
    with _session_lock:
        _destroy_session_locked()


def has_model() -> bool:
    return os.path.exists(model_onnx_path())


def _standardize(feats: np.ndarray, meta: Dict) -> np.ndarray:
    """用 train_meta 中的 feature_mean/std 做标准化；缺省时退化为恒等。"""
    mean = np.asarray(meta.get('feature_mean', [0.0] * INPUT_DIM), dtype=np.float32).reshape(1, -1)
    std = np.asarray(meta.get('feature_std', [1.0] * INPUT_DIM), dtype=np.float32).reshape(1, -1)
    std = np.where(std == 0, 1.0, std)
    return (feats.reshape(1, -1) - mean) / std


def predict_forget_probability(features) -> Optional[float]:
    """
    给定 8 维特征，输出遗忘概率 0~1。

    - 输入校验不通过 / 无模型 / 推理异常时返回 None（调用方回退规则）。
    - 推理异常时销毁会话并重试一次。
    """
    if not _validate_features(features):
        return None
    sess = _get_session()
    if sess is None:
        return None
    meta = _load_meta()
    x = _standardize(_clamp_features(features), meta)
    for attempt in range(2):
        try:
            out = sess.run(['prob'], {'features': x})[0]
            p = float(np.asarray(out).reshape(-1)[0])
            if not math.isfinite(p):
                return None
            # 模型导出输出的是原始 logits（无 Sigmoid），推理端手动执行 sigmoid
            p = 1.0 / (1.0 + np.exp(-p))
            # clip 到 [0,1]，保证遗忘概率合法
            return float(np.clip(p, 0.0, 1.0))
        except Exception as e:
            _log(f"[memory_model] onnx 推理失败(第{attempt + 1}次): {e}")
            reset_session()
            sess = _get_session()
            if sess is None:
                return None
    return None


def predict_full_state(features) -> Optional[Tuple[float, float, float]]:
    """
    多输出头推理：输入 8 维特征，返回 (forget_prob, stability, difficulty)。

    - forget_logits 由推理端手动 sigmoid 映射到 [0,1]；
    - stability / difficulty 已在模型内经过 softplus / sigmoid，此处仅 clip 到合法区间；
    - 输入非法 / 无模型 / 推理异常时返回 None（调用方回退 SM-2）。
    """
    if not _validate_features(features):
        return None
    sess = _get_session()
    if sess is None:
        return None
    meta = _load_meta()
    x = _standardize(_clamp_features(features), meta)
    for attempt in range(2):
        try:
            out = sess.run(['forget_logits', 'stability', 'difficulty'], {'features': x})
            forget_logits = float(np.asarray(out[0]).reshape(-1)[0])
            stability = float(np.asarray(out[1]).reshape(-1)[0])
            difficulty = float(np.asarray(out[2]).reshape(-1)[0])
            if not all(math.isfinite(v) for v in (forget_logits, stability, difficulty)):
                return None
            # forget_logits -> sigmoid -> forget_prob
            forget_prob = 1.0 / (1.0 + np.exp(-forget_logits))
            # clip 到合法区间
            return (
                float(np.clip(forget_prob, 0.0, 1.0)),
                float(np.clip(stability, 0.5, 30.0)),
                float(np.clip(difficulty, 0.1, 0.9)),
            )
        except Exception as e:
            _log(f"[memory_model] predict_full_state 推理失败(第{attempt + 1}次): {e}")
            reset_session()
            sess = _get_session()
            if sess is None:
                return None
    return None


def predict_states(features) -> Optional[Tuple[float, float, float]]:
    """
    MODE_B 专用：返回 (forget_prob, stability_delta, difficulty_delta)。
    模型非 3 输出 / 输入非法 / 异常时返回 None。
    """
    if OUTPUT_DIM != 3:
        return None
    if not _validate_features(features):
        return None
    sess = _get_session()
    if sess is None:
        return None
    meta = _load_meta()
    x = _standardize(_clamp_features(features), meta)
    try:
        out = sess.run(['prob', 'stab_delta', 'diff_delta'], {'features': x})
        prob = float(np.asarray(out[0]).reshape(-1)[0])
        stab = float(np.asarray(out[1]).reshape(-1)[0])
        diff = float(np.asarray(out[2]).reshape(-1)[0])
        if not all(math.isfinite(v) for v in (prob, stab, diff)):
            return None
        return max(0.0, min(1.0, prob)), max(-1.0, min(1.0, stab)), max(0.0, min(1.0, diff))
    except Exception as e:
        _log(f"[memory_model] MODE_B 推理失败: {e}")
        reset_session()
        return None


# ============================ 模型健康检查 ============================

def model_health_check() -> Dict:
    """
    模型自检：检查 onnx / pth / train_meta 完整性，返回健康状态与故障原因。
    上层可据此决定是否强制重训或降级 SM-2。
    """
    problems: List[str] = []

    onnx_path = model_onnx_path()
    if not os.path.exists(onnx_path):
        problems.append("onnx 文件缺失")
    elif os.path.getsize(onnx_path) == 0:
        problems.append("onnx 文件为空/损坏")

    pth_path = model_pth_path()
    if not os.path.exists(pth_path):
        problems.append("pth 文件缺失")

    meta = _load_meta()
    if not meta:
        problems.append("train_meta 缺失或损坏")
    else:
        mean = meta.get('feature_mean')
        std = meta.get('feature_std')
        if mean is None or std is None:
            problems.append("train_meta 缺少 feature_mean/feature_std")
        else:
            mean_arr = np.asarray(mean, dtype=np.float32)
            std_arr = np.asarray(std, dtype=np.float32)
            if not np.isfinite(mean_arr).all():
                problems.append("feature_mean 非法(含 NaN/inf)")
            if not np.isfinite(std_arr).all():
                problems.append("feature_std 非法(含 NaN/inf)")
            if (std_arr == 0).all():
                problems.append("feature_std 全零")

    return {'healthy': len(problems) == 0, 'problems': problems}


# ============================ 间隔换算 ============================

def calc_next_interval(forget_prob, stability=1.0) -> int:
    """平滑间隔公式：interval = stability * (1 - forget_prob)^1.5。"""
    p = max(0.0, min(1.0, float(forget_prob)))
    s = max(0.3, float(stability or 1.0))

    # DEBUG：打印输入 forget_prob、stability
    _log(f"[DEBUG-CALC] forget_prob={p}, stability={s}")

    # 调试模式：DEV_FORCE_SKIP_SAMPLE_THRESHOLD=True 时把 stability 放大 4 倍（仅调试生效）
    if DEV_FORCE_SKIP_SAMPLE_THRESHOLD:
        s = s * 4.0

    base = (1.0 - p) ** 1.5          # 中间计算值 (1 - forget_prob)^1.5
    interval_float = s * base        # 原始未 round 的 interval 浮点值
    # DEBUG：打印中间计算值与原始 interval
    _log(f"[DEBUG-CALC] (1-p)^1.5={base}, raw_interval={interval_float}")

    interval = round(interval_float)
    return int(max(1, min(365, interval)))


def calc_next_interval_sm2(is_right, gap_days, stability=1.0) -> int:
    """简化 SM-2（回退规则）：答对间隔翻倍，答错回到 1 天。"""
    if is_right:
        return int(max(1, min(365, max(1, int(gap_days or 1)) * 2)))
    return 1


def recommend_interval(word_id, is_right, gap_days) -> dict:
    """
    综合给出复习建议。返回 dict（字段与历史版本完全一致）：
      interval       下次间隔（天）
      forget_prob    预测遗忘概率（None 表示未用模型）
      new_stability / new_difficulty / new_lapses  更新后的记忆状态
      used_model     是否使用了神经网络
    """
    word = db.get_word_by_id(word_id)
    stability = float(word['stability']) if word and word.get('stability') else 1.0
    difficulty = float(word['difficulty']) if word and word.get('difficulty') else 0.5
    lapses = int(word['lapses']) if word and word.get('lapses') else 0

    forget_prob: Optional[float] = None
    pred_stability: Optional[float] = None
    pred_difficulty: Optional[float] = None
    used_model = False
    stab_delta: Optional[float] = None
    diff_delta: Optional[float] = None

    _log(f"[DEBUG-MODEL] has_model={has_model()}, DEV_FORCE_SKIP={DEV_FORCE_SKIP_SAMPLE_THRESHOLD}, review_cnt={db.get_record_count('review')}, MIN={MIN_TRAIN_SAMPLES}")
    if has_model() and (DEV_FORCE_SKIP_SAMPLE_THRESHOLD or db.get_record_count('review') >= MIN_TRAIN_SAMPLES):
        feats = extract_features(word_id)
        if feats is not None:
            if MODE_A_STABLE:
                res = predict_full_state(feats)
                if res is not None:
                    forget_prob, pred_stability, pred_difficulty = res
            else:
                res = predict_states(feats)
                if res is not None:
                    forget_prob, stab_delta, diff_delta = res

    if MODE_A_STABLE:
        # 多输出头模式：predict_full_state 返回 (forget_prob, stability, difficulty)
        if forget_prob is not None and pred_stability is not None:
            used_model = True
            # 不再传入词库硬编码 stability，改用模型预测 stability 计算间隔
            interval = calc_next_interval(forget_prob, pred_stability)
            if is_right:
                new_stability = min(30.0, pred_stability * 1.4)
                new_lapses = lapses
            else:
                new_stability = max(0.5, pred_stability * 0.6)
                new_lapses = lapses + 1
            new_difficulty = max(0.0, min(1.0, 0.9 * pred_difficulty + (0.0 if is_right else 0.1)))
        else:
            # 模型不可用：回退简化 SM-2（用词库 stability/difficulty）
            interval = calc_next_interval_sm2(is_right, gap_days, stability)
            if is_right:
                new_stability = min(30.0, stability * 1.4)
                new_lapses = lapses
            else:
                new_stability = max(0.5, stability * 0.6)
                new_lapses = lapses + 1
            new_difficulty = max(0.0, min(1.0, 0.9 * difficulty + (0.0 if is_right else 0.1)))
    else:
        # 实验模式：网络预测 stability/difficulty 增量，替换手写规则
        if forget_prob is not None and stab_delta is not None:
            used_model = True
            interval = calc_next_interval(forget_prob, stability)
            new_stability = max(0.3, min(30.0, stability * (1.0 + float(stab_delta))))
            new_difficulty = max(0.0, min(1.0, 0.9 * difficulty + float(diff_delta or 0.0)))
        else:
            interval = calc_next_interval_sm2(is_right, gap_days, stability)
            new_stability = max(0.3, min(30.0, stability * (1.4 if is_right else 0.6)))
            new_difficulty = max(0.0, min(1.0, 0.9 * difficulty + (0.0 if is_right else 0.1)))
        new_lapses = lapses + (0 if is_right else 1)

    return {
        'interval': interval,
        'forget_prob': forget_prob,
        'new_stability': round(new_stability, 4),
        'new_difficulty': round(new_difficulty, 4),
        'new_lapses': new_lapses,
        'used_model': used_model,
    }


# ============================ 训练时机 ============================

def should_train() -> bool:
    """记录数足够且（无模型或距上次训练超过阈值）则允许训练。"""
    if not ENABLE_BACKGROUND_TRAIN:
        # 正式打包发布关闭后台自动训练
        return False
    if db.get_record_count('review') < MIN_TRAIN_SAMPLES:
        return False
    if not has_model():
        return True
    meta = _load_meta()
    last = meta.get('last_train_ts', 0) or 0
    return (time.time() - last) >= RETRAIN_INTERVAL_SECONDS


# ============================ 未来演进方案（技术债务注释） ============================
"""
【时间泄露问题】
    build_training_data 使用单词“当前”特征近似“当时”特征，存在有偏近似。当前折中：
    对复习记录数少的单词样本线性降权（MIN_RECORDS_FOR_FULL_WEIGHT 以下）。

【数据库升级方案（未来实现特征快照）】
    review_records（本应用对应 records 表）增加特征快照字段，复习发生时写入当时的
    8 维特征（或写入可重建特征的原始量）。迁移 SQL 思路：

        ALTER TABLE records ADD COLUMN feat_snapshot TEXT;  -- JSON 数组，存储当时 8 维特征

    复习写入时：把 extract_features 的结果 json.dumps 存进 feat_snapshot；
    训练时优先用 feat_snapshot（有值时），否则回退当前特征近似并继续降权。
    这样彻底消除时间泄露。
"""
