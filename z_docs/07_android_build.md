# 安卓打包说明（Flet）

## 1. 架构与依赖

- UI：Flet（原生控件，含 LineChart 图表，**不使用 matplotlib**）。
- 数据：SQLite（`vocab.db`）、`settings.json`、模型文件，均放在可写数据目录。
- AI：桌面端用 PyTorch 训练并导出 `ai/memory_model.onnx`，移动端用 ONNX Runtime 做 CPU 推理。
  - 移动端**不安装 torch**（体积约 +100MB 且移动端无用），只装 `onnxruntime`。
  - 训练所需依赖见 `requirements.txt`，移动端推理依赖见 `requirements-mobile.txt`。

## 2. 路径与数据目录

`paths.py` 统一管理路径：

- 数据目录 `get_data_dir()`：
  1. 环境变量 `WORD_APP_DATA_DIR` 优先；
  2. 否则默认项目根目录（桌面端，兼容旧 `vocab.db`/`settings.json`）。
- 内置词本 `data/builtin/*.csv` 打包进应用（只读，离线可用）。

安卓端：`flet build apk` 打包后，应用私有可写目录即进程工作目录。若需显式指定，
可在启动时注入 `WORD_APP_DATA_DIR`（例如指向应用私有 files 目录），保证数据库与
设置可写。`pathlib`/`os.path` 已用于跨平台拼接，无平台硬编码绝对路径。

## 3. 桌面端：训练并导出 ONNX 模型

1. 安装完整依赖：
   ```
   pip install -r requirements.txt
   ```
2. 运行应用并正常复习，积累 ≥50 条复习记录后，应用会自动在后台训练并导出
   `ai/memory_model.onnx`（也会保存 `ai/memory_model.pth` 与 `ai/train_meta.json`）。
   - 也可手动触发训练：
     ```python
     from ai.memory_model import train_model
     train_model(force=True)
     ```
3. 确认 `ai/memory_model.onnx` 已生成（约几十 KB）。

## 4. 打包安卓 APK

1. 安装 Flet 及移动端依赖：
   ```
   pip install -r requirements-mobile.txt
   ```
2. 确保 `ai/memory_model.onnx` 存在（随项目打包进 APK）。
3. 构建 APK：
   ```
   flet build apk
   ```
   产物位于 `build/apk/`。
4. 可选：指定应用标识与名称：
   ```
   flet build apk --org com.example --project word_app --product 自适应背单词
   ```

> 说明：`flet build apk` 依赖本机 Android SDK / Java 环境；首次构建会下载较多资源，
> 请保证网络通畅。详见 Flet 官方打包文档。

## 5. 体积优化建议

- 移动端只用 ONNX Runtime（CPU EP），不装 torch。
- 模型规模很小（8→32→16→1），`.onnx` 仅数十 KB。
- 内置词本为纯文本 CSV，约 600KB，可接受。

## 6. 数据库迁移说明

数据库结构在 `data/db.py::init_db()` 中自动完成增量迁移：

- 新增 `test_records` 表（拼写测试记录）。
- `records` 表新增 `record_type` 列（`'learn'`/`'review'`）。
- 旧库无需删除：首次运行自动 `ALTER TABLE` 补列，已有数据保留。
- 如需全新初始化，删除数据目录下的 `vocab.db` 后重新启动即可（内置词本会自动重新导入）。

---

# （续）打包踩坑历程（按日期）

## 2026-08-27
- 初探 `flet build apk`：本机缺 Flutter / JDK / Android SDK / flet-cli 四项，暂无法构建。

## 2026-08-29
- 补环境：`pip install flet-cli==0.28.3`；Flutter 3.29.2；Microsoft JDK 17（`C:\Users\DavisStark\java\17.0.13+11`）；Android SDK（`platforms;android-35`、`build-tools;34.0.0`）；git（`E:\Git\cmd`）。
- 本地模板：`--template _template_cache\_extract\flet-build-template-0.28.3`；最小依赖 `pyproject.toml`（`[project] dependencies=["flet==0.28.3"]`）。
- 结论：本地打包链路基本搭通，但被文件策略回退 workspace-write（subprocess 命名管道挂起）阻塞，用户决定「先不打包了」。

## 打包方式对比
- **flet pack（exe）**：PyInstaller 打包桌面 exe；踩坑为打包后内置 csv 路径失效（已用 `paths.py` 分离资源/数据目录解决）。
- **flet build web**：产物为静态站点，需另行托管。
- **flet build apk**：依赖 Flutter + Android 工具链；GitHub Actions 打包排队 / 克隆 502 不稳定，国内网络下载易超时 → 转本地打包。

## 2026-09-03
- 打包无新进展，维持「先不打包了」；内置词本数据源由原 CSV 改为 `data/builtin` 下 7 份 JSON（`data/bank.py` 代码内合并）。
