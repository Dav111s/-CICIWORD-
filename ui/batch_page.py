# ui/batch_page.py
"""批量 OCR 识别页（短语解析 + removed 软删除标记 + JSON 状态持久化）。

- 解析：每行「英文短语(可含空格) + 空格 + 中文释义(可含空格)」，按英文/中文边界拆分，
  英文短语完整保留、不碎裂。
- 条目：英文文本 + 可编辑释义 + 移除/恢复切换按钮；removed 仅置灰标记，不物理删除，可恢复。
- 持久化：识别结果（含 removed 标记）写入本地 JSON，页面重建后不丢失。
- 保存：过滤 removed=False 的有效条目，去重写入词本，SnackBar 展示完整统计。
"""
import json
import os
import re

import flet as ft

from data import wordbooks as wb
from paths import get_data_dir
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR

_STATE_FILE = "batch_state.json"


# ---------------- 状态持久化 ----------------

def _state_path() -> str:
    """状态 JSON 路径（数据目录下，随应用数据一起持久化）。"""
    return str(get_data_dir() / _STATE_FILE)


def _load_state():
    """从 JSON 恢复上次识别结果（含 removed 标记）；缺失/损坏返回空列表。"""
    try:
        if os.path.exists(_state_path()):
            with open(_state_path(), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [{
                    'word': it.get('word', ''),
                    'trans': it.get('trans', ''),
                    'removed': bool(it.get('removed', False)),
                } for it in data]
    except Exception:
        pass
    return []


def _save_state(items):
    """把识别结果（含 removed 标记）写回 JSON；失败静默（不影响主流程）。"""
    try:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
    except Exception:
        pass


# ---------------- 连字符归一化 + 合并预处理 ----------------

# 连字符/破折号家族：OCR 常把 ASCII '-' 识别成这些非 ASCII 字符，统一归一化
_HYPHENS = "-‐‑‒–—―−"


def _normalize_hyphens(text: str) -> str:
    """把非 ASCII 连字符/破折号统一替换为 ASCII '-'，避免被解析当成中文起点。"""
    if not text:
        return text
    for ch in _HYPHENS[1:]:  # 跳过 ASCII '-' 本身
        text = text.replace(ch, "-")
    return text


def preprocess_merge_hyphen(text: str) -> str:
    """预处理：用 pending_prefix 缓存半段英文碎片，合并被断行的连字符复合词。

    - 无空格行 = 半段英文碎片，缓存进 pending_prefix（不丢弃，可能带结尾连字符）；
    - pending_prefix 非空且遇到带空格完整词条，三种合并方式：
        · 当前行以 '-' 开头：`pending.rstrip('-') + '-' + 当前行.lstrip('-')`
        · 否则碎片以 '-' 结尾：`pending + 当前行`（保留结尾连字符，如 profit- + driven）
        · 否则：空格拼接两段
    - 正常完整词条（英文 + 空格 + 释义）直接加入结果；
    - 遍历结束若 pending_prefix 仍有残留，直接丢弃，不生成无效条目。
    """
    if not text:
        return text
    out = []
    pending_prefix = None  # 缓存无空格的半段英文碎片

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue  # 空行跳过
        if " " not in line:
            # 无空格 -> 半段英文碎片，缓存，不丢弃
            pending_prefix = line
            continue
        # 有空格 -> 完整词条
        if pending_prefix is not None:
            # 存在缓存碎片 -> 合并（兼容 开头/结尾 连字符两种断行）
            if line.startswith("-"):
                merged = f"{pending_prefix.rstrip('-')}-{line.lstrip('-')}"
            elif pending_prefix.endswith("-"):
                merged = f"{pending_prefix}{line}"
            else:
                merged = f"{pending_prefix} {line}"
            out.append(merged)
            pending_prefix = None
        else:
            out.append(line)  # 正常完整词条直接保留
    # 残留的 pending_prefix 直接丢弃，不写入结果
    return "\n".join(out)


# ---------------- 短语解析 ----------------

def _parse_input(text):
    """按行解析「英文短语 中文释义」。

    - 英文短语可含空格、中文释义可含空格；
    - 分隔点 = 英文(ASCII) 与 中文(非 ASCII) 的边界；
    - 无中文 / 无英文 / 脏行丢弃；重复短语去重（保留首次）。
    返回 [{'word','trans','removed'}]。
    """
    text = _normalize_hyphens(text)        # 先统一连字符/破折号为 ASCII '-'
    text = preprocess_merge_hyphen(text)   # 再合并断行的连字符复合词
    result = []
    seen = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # 找第一个非 ASCII 字符（中文释义起点）
        split_idx = -1
        for i, ch in enumerate(line):
            if ord(ch) > 127:
                split_idx = i
                break
        if split_idx <= 0:
            continue  # 无中文或无英文 -> 丢弃
        phrase = line[:split_idx].strip().lower()
        trans = line[split_idx:].strip()
        # 英文部分必须是合法短语（字母/空格/连字符/撇号）
        if not phrase or not re.fullmatch(r"[A-Za-z][A-Za-z'’\- ]*", phrase):
            continue
        if phrase in seen:
            continue
        seen.add(phrase)
        result.append({'word': phrase, 'trans': trans, 'removed': False})
    return result


def build_batch_page(page: ft.Page) -> ft.Control:
    input_field = ft.TextField(
        label="粘贴单词/短语（每行「短语 释义」）",
        multiline=True, min_lines=4, max_lines=8,
    )
    run_btn = glass_button(
        "开始识别", lambda e: _run(page),
        tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900,
    )

    result_list = ft.ListView(expand=True, spacing=8)

    clear_btn = glass_button("清空结果", lambda e: _clear_results(page))
    confirm_btn = glass_button(
        "确认保存", lambda e: _open_save_dialog(page),
        tint=ft.Colors.BLUE_400, opacity=0.32, text_color=ft.Colors.BLUE_900,
    )
    bottom_bar = ft.Container(
        content=ft.Row([clear_btn, confirm_btn], alignment=ft.MainAxisAlignment.END, spacing=8),
        padding=ft.padding.only(left=12, right=12, top=10, bottom=12),
        bgcolor=ft.Colors.with_opacity(0.20, ft.Colors.WHITE),
        border=ft.border.only(top=ft.BorderSide(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE))),
        border_radius=ft.border_radius.only(top_left=16, top_right=16),
    )

    # 恢复上次识别结果（含 removed 标记，页面重建不丢失）
    page.batch_results = _load_state()
    page.batch_input = input_field
    page.batch_result_list = result_list
    page.confirm_btn = confirm_btn

    if page.batch_results:
        _rebuild_list(page)
    else:
        result_list.controls.append(ft.Text("粘贴单词/短语后点击「开始识别」", color=SUB_TEXT_COLOR))

    # 初始保存按钮状态（构建期直接赋值，不触发 update）
    confirm_btn.disabled = not _has_effective(page)
    confirm_btn.opacity = 0.4 if confirm_btn.disabled else 1.0

    back_btn = glass_button("返回词库", lambda e: page.go("/wordbook"))

    return page_shell(
        page,
        ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [back_btn, ft.Text("批量识别", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    input_field,
                    ft.Row([run_btn], alignment=ft.MainAxisAlignment.END),
                    result_list,
                    bottom_bar,
                ],
                spacing=10,
                expand=True,
            ),
            expand=True,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    )


def _run(page: ft.Page):
    """解析输入、组装条目、持久化并重建列表。"""
    page.batch_results = _parse_input(page.batch_input.value or "")
    _save_state(page.batch_results)
    if not page.batch_results:
        page.batch_result_list.controls.clear()
        page.batch_result_list.controls.append(ft.Text("请先粘贴单词/短语", color=SUB_TEXT_COLOR))
    else:
        _rebuild_list(page)
    page.batch_result_list.update()
    _refresh_confirm(page)


def _rebuild_list(page: ft.Page):
    """按 batch_results 重建结果列表（重建会重新绑定每条索引）。"""
    page.batch_result_list.controls.clear()
    for idx in range(len(page.batch_results)):
        page.batch_result_list.controls.append(_build_tile(page, idx))


def _build_tile(page: ft.Page, idx: int) -> ft.Control:
    """单条结果：英文短语 + 可编辑释义 + 移除/恢复切换按钮；removed 整行置灰。"""
    it = page.batch_results[idx]
    removed = bool(it.get('removed'))

    trans_field = ft.TextField(
        value=it['trans'] or "",
        dense=True,
        hint_text="释义（可编辑）",
        text_size=14,
        on_change=lambda e, i=idx: _on_trans_edit(page, i, e.control.value),
    )

    tile = glass(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(it['word'], size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.RESTORE if removed else ft.Icons.CLOSE,
                            icon_size=16,
                            tooltip="恢复" if removed else "移除",
                            icon_color=ft.Colors.GREY,
                            on_click=lambda e, i=idx: _toggle_removed(page, i),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                trans_field,
            ],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=10, radius=12,
    )
    # removed 状态：整行置灰（软删除，不物理移除）
    return ft.Container(content=tile, opacity=0.4 if removed else 1.0)


def _on_trans_edit(page: ft.Page, idx: int, value: str):
    """编辑释义：写回内存并持久化。"""
    page.batch_results[idx]['trans'] = value
    _save_state(page.batch_results)


def _toggle_removed(page: ft.Page, idx: int):
    """切换 removed 标记（软删除），置灰/恢复，物理上不删除条目。"""
    it = page.batch_results[idx]
    it['removed'] = not bool(it.get('removed'))
    _rebuild_list(page)
    _save_state(page.batch_results)
    page.batch_result_list.update()
    _refresh_confirm(page)


def _clear_results(page: ft.Page):
    """清空全部识别结果并持久化。"""
    page.batch_results = []
    _save_state(page.batch_results)
    page.batch_result_list.controls.clear()
    page.batch_result_list.controls.append(ft.Text("识别结果已清空", color=SUB_TEXT_COLOR))
    page.batch_result_list.update()
    _refresh_confirm(page)


def _has_effective(page: ft.Page) -> bool:
    """是否存在 removed=False 的有效条目。"""
    return any(not it.get('removed') for it in (page.batch_results or []))


def _refresh_confirm(page: ft.Page):
    """没有有效条目时，底部【确认保存】置灰不可点击。"""
    enabled = _has_effective(page)
    page.confirm_btn.disabled = not enabled
    page.confirm_btn.opacity = 1.0 if enabled else 0.4
    page.update()


# ---------------- 保存模态弹窗 ----------------

def _open_save_dialog(page: ft.Page):
    def _refresh():
        is_new = radio.value == "new"
        name_field.visible = is_new
        dropdown.visible = not is_new
        valid = bool((name_field.value or '').strip()) if is_new else bool(dropdown.value)
        ok_btn.disabled = not valid
        name_field.update()
        dropdown.update()
        ok_btn.update()

    def _confirm(e):
        if ok_btn.disabled:
            return
        _do_save(page, radio.value, name_field.value, dropdown.value, dialog)

    radio = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(value="new", label="保存到新词本"),
                ft.Radio(value="existing", label="添加到已有词本"),
            ],
            spacing=16, wrap=True,
        ),
        value="new",
        on_change=lambda e: _refresh(),
    )
    name_field = ft.TextField(label="新词本名称", dense=True, on_change=lambda e: _refresh())
    dropdown = ft.Dropdown(
        label="选择已有词本", dense=True,
        options=[ft.dropdown.Option(key=b[0], text=f"{b[0]}（{b[3]} 词）")
                 for b in wb.list_wordbooks() if not b[2]],
        on_change=lambda e: _refresh(),
    )
    ok_btn = ft.ElevatedButton("确定保存", on_click=_confirm)
    cancel_btn = ft.TextButton("取消", on_click=lambda e: page.close(dialog))

    dialog = ft.AlertDialog(
        title=ft.Text("保存识别结果"),
        content=ft.Column([radio, name_field, dropdown], spacing=12, tight=True),
        actions=[cancel_btn, ok_btn],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    dropdown.visible = False
    ok_btn.disabled = True
    page.open(dialog)


def _do_save(page: ft.Page, mode: str, name_value: str, dropdown_value: str, dialog):
    """保存：过滤 removed=False 的有效条目，去重写入词本，SnackBar 展示统计。"""
    items = page.batch_results or []
    total = len(items)                                   # 总识别条数
    removed_count = sum(1 for it in items if it.get('removed'))  # 被标记移除条数
    effective = [it for it in items if not it.get('removed')]
    savable = [(it['word'], it['trans']) for it in effective if (it['trans'] or '').strip()]

    if not savable:
        _snack(page, "没有可保存的有效条目（释义为空）", ft.Colors.RED)
        return

    if mode == "new":
        name = (name_value or '').strip()
        if not name:
            _snack(page, "请输入新词本名称", ft.Colors.RED)
            return
        if not wb.create_wordbook(name):
            _snack(page, f"词本「{name}」已存在，请换个名称", ft.Colors.RED)
            return
    else:
        name = dropdown_value
        if not name:
            _snack(page, "请先选择已有词本", ft.Colors.RED)
            return

    saved, skipped = wb.add_words_to_book(name, savable)  # 词本去重：英文一致直接跳过
    page.close(dialog)
    _clear_results(page)
    _snack(
        page,
        f"总识别 {total} 条，移除 {removed_count} 条，新增 {saved} 条，重复跳过 {skipped} 条",
        ft.Colors.GREEN,
    )


def _snack(page: ft.Page, msg: str, color):
    page.open(ft.SnackBar(ft.Text(msg), bgcolor=color))
