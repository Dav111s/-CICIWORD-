word_app/
├── main.py                  # 程序入口，Flet 页面路由控制
├── config.py                # 全局配置常量
├── ai/
│   └── memory_model.py      # 遗忘预测神经网络（PyTorch 训练 + ONNX 推理，双运行模式）
├── data/
│   ├── db.py                # SQLite 数据库初始化、单词/记录增删改查
│   ├── csv_loader.py        # CSV 词库导入解析
│   └── statistics.py        # 学习统计计算（正确率、进度、图表数据）
├── ui/
│   ├── home_page.py         # 首页总览（今日任务、进度条）
│   ├── wordbook_page.py     # 词库管理页（导入/查看词本）
│   ├── review_page.py       # 单词卡片复习页（翻面、记住/忘记）
│   └── stats_page.py        # 数据统计页（图表展示）
└── z_docs/                  # 存放毕设文档、截图、流程图等

---

# （续）架构迭代开发日志（按日期）

## 2026-08-26
- 初始架构：`main.py` 页面路由 + `data/`（db、csv_loader、statistics）+ `ui/`（home/wordbook/review/stats）。
- 数据存储：SQLite（`vocab.db`）+ `settings.json`。

## 2026-08-27
- `paths.py` 统一路径：可写数据目录（`WORD_APP_DATA_DIR` 优先 / 项目根目录回退）+ 只读内置词本目录 `data/builtin`。

## 2026-08-28
- 新增 `ai/memory_model.py`（PyTorch 训练 → ONNX 推理）、`data/scheduler.py`（艾宾浩斯阶梯）。
- `ui/theme.py` 统一主题与毛玻璃组件（`glass` / `glass_button` / `page_shell`）。
- 页面扩展到 12+ 路由（学习/复习/拼写/收藏/词本详情/统计/设置/小结等）。

## 2026-08-29
- 打包资源本地缓存（flet 构建模板）；数据目录策略定型（内置词本只读打包，可写数据目录分离）。

## 2026-09-03
- `srs.py`：三档 SRS 模块（`ReviewFeedback` 记住/模糊/忘记、`SrsRecord`/`SrsHistory`、`prob_to_interval`、`process_review_feedback`；表 `srs_records` / `srs_history`）。
- 数据管线：
  - `data/universe.py`：通用总词库 `universe.csv`（14686 词）+ 学段筛选 `stage_words.json`。
  - `data/word_matcher.py`：清洗去重 + 匹配 + 学段标注。
  - `data/wordbooks.py`：`wordbooks` 表（name/remark/is_builtin）+ `words.is_builtin` 列；内置词本种子 + 自定义 CRUD。`wordbooks` 表为 UI 词本列表唯一来源，旧 `book_name`（如「四级核心词汇」）成为孤儿数据（无害）。
- 路由新增 `/batch`；`main.py` 改用 `wordbooks.init_wordbooks()`。
- 复习调度：`db.submit_review_three_tier`（V1 启发式，`use_neural=False`）替换艾宾浩斯；学习三关流程不动。
- 数据管线代码化：新增 `data/bank.py`（`merge_bank()` 读取 `data/builtin` 下 7 份 JSON 数据源，合并总词库 + 重建 7 分类 `stage_words.json`），替代原独立脚本 `_build_universe.py`。
- `data/wordbooks.py`：`BUILTIN_STAGES` 由 5 套扩为 7 套（新增托福/SAT）；`init_wordbooks()` 启动时调用 `bank.merge_bank()` 并种子 7 套内置词本，只新增不删除。
- `wordbooks.search_words()`：词本内检索，只查 SQLite `words` 表（不读 CSV、不遍历目录）。
- `universe.get_stage_tags()`：7 类科目标签（含托福/SAT），供学习/复习页标注；收藏移除复用 `db.set_word_favorite(id, 0)`。

## AI 记忆模型（memory_model）

### 模块职责与数据流
- 训练阶段才导入 torch；移动端运行时只依赖 onnxruntime；模型缺失/样本不足自动回退简化 SM-2；后台线程异步训练不阻塞 UI。
- 训练数据流：`records` 表 → `build_training_data`（样本清洗 + 时间泄露降权）→ 8:2 切分 → 特征标准化（mean/std 存入 `train_meta`）→ PyTorch 训练（加权 BCE/MSE + early-stop）→ 双输出 `model.pth` + `model.onnx`。
- 推理数据流：`word_id` → `extract_features`（LRU-TTL 缓存）→ 输入校验 + 值域裁剪 → 标准化 → ONNX 推理 → 遗忘概率 → 间隔换算；失败降级简化 SM-2。

### 两种运行模式
- **MODE_A_STABLE**（默认开启）：网络只输出遗忘概率；stability/difficulty/lapses 由手写规则更新。
- **MODE_B_EXPERIMENT**（实验）：网络同时输出遗忘概率 + stability 增量 + difficulty 增量，替换手写规则。
- 区别：MODE_B 输出维度为 3（MODE_A 为 1），模型结构不同，切换后需重新训练。
- 风险：MODE_B 的增量训练标签源自手写规则近似，样本少时易过拟合，仅建议实验评估、不用于生产。

### 训练流程
样本清洗（过滤 NaN/inf/越界）→ 时间泄露降权（复习记录数少的单词样本线性降权）→ 8:2 切分 → 特征标准化（mean/std 存 `train_meta`，推理复用）→ 加权 BCE（遗忘概率）+ MSE（增量）+ early-stop → `torch.save(.pth)` + `torch.onnx.export(.onnx)` → 后台线程 `train_async` 不阻塞 UI。

### 推理流程
`extract_features`（LRU-TTL 缓存）→ `_validate_features` 输入校验 + `_clamp_features` 值域裁剪 → `_standardize` 标准化 → ONNX 推理（会话锁 + 加载/推理失败销毁重建重试）→ 失败降级简化 SM-2；`model_health_check()` 自检 onnx/pth/meta 完整性。

### 文件产出清单
- `model.pth`：PyTorch 权重（桌面训练产物）
- `model.onnx`：ONNX 推理模型（移动端使用）
- `train_meta.json`：num_samples、last_train_ts、feature_mean、feature_std、mode、output_dim

### 已知技术债务
- 时间泄露：`records` 表未保存每条记录“当时”的特征快照，训练用“当前”特征近似当时状态，有偏。
- 折中方案：对复习记录数少的单词样本线性降权（`MIN_RECORDS_FOR_FULL_WEIGHT` 以下）。
- 未来演进：`records` 表增加 `feat_snapshot` 字段（JSON 数组存储当时 8 维特征），训练优先用快照，彻底消除时间泄露。

### 外部接口列表
- `recommend_interval(word_id, is_right, gap_days) -> dict`：唯一对外 API，返回字段（interval/forget_prob/new_stability/new_difficulty/new_lapses/used_model）保持不变。
- `model_health_check() -> dict`：新增运维接口，返回 `healthy` + `problems`。
- `set_log_callback(fn)`：日志回调扩展点，上层注入文件日志等处理器（不硬编码 print）。
- `has_model()` / `should_train()` / `train_model()` / `train_async()`：内部训练时机与推理辅助接口。

## SRS 调度流程（data/db.py）

### 统一入口
- 学习模式通关（`stage>=3` 且答对）与复习模式，两条路径**统一走 `memory_model.recommend_interval(word_id, is_right, gap_days)`**。
- 学习模式通关调用新增内部辅助函数 `_learn_completion_interval(word_id, review_day)`，内部调用 `recommend_interval(..., is_right=True, gap_days)`。

### 历史债务
- 旧版本学习模式通关硬编码走艾宾浩斯阶梯 `get_ebbinghaus_interval(streak+1)`；`get_word_streak` 在通关时恒为 2（末尾两条永远是「第一关答对 + 第二关答对」），导致 `new_streak=3`、`EBBINGHAUS_LADDER[2]=4` 天，所有单词间隔固定 4 天、无区分。
- 现改为学习通关也走 `recommend_interval`，遗忘概率公式 / SM-2 回退 + stability 更新统一生效。

### 数据流（记忆状态落库）
- 学习模式答错：`stage` 重置为 1，同时 `lapses += 1` 并写库。
- 学习模式通关：`recommend_interval` 返回的 `new_stability / new_difficulty / new_lapses` 写入 `words` 表；`forget_prob` 写入 `records.predicted_prob`。
- 学习阶段即持久化 stability/difficulty/lapses，不再只有复习模式更新。

### 降级策略
- `memory_model` 导入失败 / 异常：`_learn_completion_interval` 捕获异常，回退旧的艾宾浩斯阶梯 `get_ebbinghaus_interval(streak+1)`，stability/difficulty/lapses 保持原值。
- 复习模式 `_review_interval` 原有降级逻辑不变。

## 技术对比记录
- **Flet vs Flutter**：Flet 用 Python 直接写 UI、原生控件渲染，免 Dart 工具链；Flutter 需 Dart + 完整 Android/Gradle 链路，打包更重。项目以 Python 为主，故选 Flet。
- **Python 本地打包难点**：
  - `flet pack`（exe）走 PyInstaller，打包产物运行目录与开发目录不同，内置 csv 需用 `paths.py` 分离只读资源 / 可写数据目录。
  - `flet build apk` 依赖 Flutter + JDK + Android SDK，国内网络下载 Gradle / 模板易超时，需本地缓存模板 + 最小依赖。