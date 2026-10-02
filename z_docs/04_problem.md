# 踩坑记录（按日期）

> 逐条记录问题与当时确定的解决方案。

## 2026-08-27
- **`flet build` 报 WinError 5（权限不足）**：缺 flet-cli 且目录权限受限。
  - 解决：以管理员运行 `pip install flet-cli==0.28.3`（或 `pip install "flet[all]==0.28.3" --upgrade`）。

## 2026-08-28
- **flet 0.28.3 无 `ft.colors` / `ft.ImageFilter` / `image_filter`**：只有 `ft.Colors`（大写）。
  - 解决：颜色全部用 `ft.Colors.X`；不做 BackdropFilter。
- **`Container.blur` 序列化异常（值为 None）**：毛玻璃无法用 blur 实现。
  - 解决：改用半透明 `bgcolor`（`ft.Colors.with_opacity`）+ 柔光描边 + 低透明度阴影模拟磨砂。
- **exe 打包后无法加载 CSV**：内置词本路径在打包产物中失效。
  - 解决：`paths.py` 区分「只读内置资源」（`data/builtin`，随应用打包）与「可写数据目录」（`vocab.db` / `settings.json`，走 `WORD_APP_DATA_DIR` 或项目根目录）。

## 2026-08-29
- **git clone 502**（下载失败/服务端或网络）。
  - 解决：重试；打包资源改走本地缓存模板。
- **GitHub Actions 打包排队**：CI 队列慢、不稳定。
  - 解决：放弃 CI 打包，转本地打包。
- **flet build apk 网络超时**：下载 Gradle / Flutter 资源超时。
  - 解决：本地模板 `_template_cache\_extract\flet-build-template-0.28.3` + 最小依赖 `pyproject.toml`（仅 `flet==0.28.3`）。

## 2026-09-03
- **「新建词本」按钮点击无响应**：根因是 flet 0.28.3 移除了 `page.dialog` / `page.snack_bar`，旧写法 `page.dialog = dlg` 静默无效。
  - 解决：改用 `page.open(dialog)` / `page.close(dialog)`；提示改 `page.open(ft.SnackBar(...))`。
- **网页下载 github 资源卡顿/断连**：下载 托福 JSON 时 `ConnectionResetError [WinError 10054]`。
  - 解决：请求加 `User-Agent` + 5 次重试 + 指数退避（并跳过已存在且 >1KB 的缓存文件）。
- **首次 `submit_review_three_tier` 报 `no such table: srs_records`**。
  - 解决：`load_srs_record` 前先调用 `srs_mod.init_srs_schema(db_path)` 建表。
- **20000 词缺口**：5 套学段词表高度重叠（中考⊂高考⊂四级⊂六级⊂考研），去重后仅 7835 词；补托福+SAT 后 14686 词，仍不足 20000。
  - 取舍：用户决定停下载扩充，保留 14686 词，后续本地追加词条。
- **词本重名静默成功**：`create_wordbook` / `rename_wordbook` 名称冲突时仍返回 True。
  - 解决：冲突时返回 False（`INSERT OR IGNORE` 判 `rowcount`；重命名前查重），让「名称已存在」提示生效。
- **7 份全量 JSON 与 universe.csv 词集差异**：全量 JSON 单词语料 14658 个已全部包含在 universe.csv（14686）中，本次合并新词追加数 = 0；另有 28 个旧词来自原 CSV 词库，保留不删。
- **全量 JSON 含 phrases 多词字段**：清洗时只取 `word` 字段，并用正则排除含空格的多词短语，仅保留单词语条。
