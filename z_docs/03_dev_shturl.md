# 开发命令与路由（开发日志）

> 按对话日期记录本地启动命令、路由、调试方式的变更。

## 2026-08-26
- 运行应用：`task_app\.venv` 虚拟环境（`C:\Users\DavisStark\PycharmProjects\task_app\.venv`）运行 `main.py`。
- 跑脚本：`word_app\.venv\Scripts\python.exe`（`C:\Users\DavisStark\PycharmProjects\word_app\.venv`）。
- 入口：`ft.app(target=main, assets_dir="assets")`，窗口 9:16 手机竖屏基准（360×640）。

## 2026-08-27
- 路径管理：`paths.py` 统一数据目录（环境变量 `WORD_APP_DATA_DIR` 优先，否则项目根目录）与内置词本只读目录 `data/builtin`。

## 2026-08-28
- 路由（页面）：
  - `/` 首页、`/wordbook` 词库、`/learn` 学习、`/review` 复习、`/spelling` 拼写、
  - `/summary` 分组小结、`/learn_stats` 学习完成统计、`/stats` 统计、`/settings` 设置、
  - `/favorites` 收藏、`/book_detail` 词本详情。

## 2026-08-29
- 打包相关命令见 `07_android_build.md` / `09_apk_build.md`（flet-cli、模板缓存、JDK17 等）。

## 2026-09-03
- 新增路由 `/batch`（批量识别）。
- 启动接线变更：`main.py` 由 `import_builtin_wordbooks()` 改为 `wordbooks.init_wordbooks()`。
- 数据构建脚本：`_build_universe.py`（下载 genkin-he `json_simple` 的 中考/高考/托福/SAT JSON + 读取 `level4/6/kaoyan.csv` → 生成 `data/universe.csv` + `data/stage_words.json`）。
- 调试方式变更：
  - **flet 0.28.3 API 校验**：用 `hasattr(ft.Page, 'dialog')` 等探测，确认 `page.dialog` / `page.snack_bar` 已移除，改用 `page.open(control)` / `page.close(control)`。
  - **隔离验证**：设置 `WORD_APP_DATA_DIR` 到临时目录，跑 CRUD 断言 + 假 `Page` 跑页面构建（不污染正式 `vocab.db`）。
  - **图标/颜色校验**：`hasattr(ft.Icons, 'X')`；颜色一律 `ft.Colors.X`（大写），不用 `ft.colors`。
- 数据构建改为代码内完成：`data/bank.py::merge_bank()`（不再用 `_build_universe.py` 独立脚本），启动时 `init_wordbooks()` 自动调用。
- 控制台日志：启动时输出 7 套内置词本各自加载单词数量。
