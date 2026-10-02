# ui/wordbook_page.py
"""词库管理页：两段式抽屉折叠布局。

- 内置词本（只读）：5 套学段词本，由通用总词库 + 筛选规则生成，折叠收纳。
- 我的自定义词本（可编辑）：新建 / 重命名 / 备注 / 删除 / 导入 CSV / 批量识别，折叠收纳。
"""
import flet as ft

from data import wordbooks as wb
from config import get_current_book, set_current_book
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR


def _book_tile(page, name, remark, count, is_builtin) -> ft.Control:
    """词本条：标题 + 副标题 + 操作按钮（内置只读，自定义可编辑）。"""
    current = get_current_book()

    subtitle_parts = [f"{count} 个单词"]
    if remark:
        subtitle_parts.append(remark)
    if name == current:
        subtitle_parts.append("当前使用中")

    title_row = ft.Row(
        [
            ft.Icon(
                ft.Icons.LOCK_OUTLINE if is_builtin else ft.Icons.FOLDER_OPEN,
                size=18, color=ft.Colors.GREY,
            ),
            ft.Text(name, size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR, expand=True),
        ],
        spacing=8,
    )

    actions = [
        ft.TextButton(
            "设为当前",
            icon=ft.Icons.CHECK_CIRCLE if name == current else ft.Icons.CIRCLE_OUTLINED,
            on_click=lambda e, n=name: set_current_book_and_refresh(page, n),
        ),
    ]
    if not is_builtin:
        actions += [
            ft.TextButton("重命名", icon=ft.Icons.EDIT, on_click=lambda e, n=name: open_rename_dialog(page, n)),
            ft.TextButton("备注", icon=ft.Icons.NOTES, on_click=lambda e, n=name, r=remark: open_remark_dialog(page, n, r)),
            ft.TextButton("删除", icon=ft.Icons.DELETE, on_click=lambda e, n=name: open_delete_dialog(page, n)),
        ]

    return glass(
        ft.Column(
            [
                title_row,
                ft.Text(" · ".join(subtitle_parts), size=12, color=ft.Colors.GREY),
                ft.Row(actions, spacing=2, wrap=True),
            ],
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        ),
        radius=14,
        padding=12,
        on_click=lambda e, n=name: open_book_detail(page, n),
    )


def _section(icon, title, controls, initially_expanded) -> ft.ExpansionTile:
    """折叠抽屉：标题栏 + 展开后显示 controls。"""
    return ft.ExpansionTile(
        title=ft.Row(
            [ft.Icon(icon, size=20, color=SUB_TEXT_COLOR),
             ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)],
            spacing=8,
        ),
        controls=[controls],
        initially_expanded=initially_expanded,
        maintain_state=True,
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.WHITE),
        collapsed_bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
        text_color=TEXT_COLOR,
        icon_color=SUB_TEXT_COLOR,
        shape=ft.RoundedRectangleBorder(radius=14),
        collapsed_shape=ft.RoundedRectangleBorder(radius=14),
        controls_padding=ft.padding.only(top=4, bottom=4),
    )


def _run_search(page: ft.Page):
    """实时过滤已加载词本内的单词（输入文字即时检索，不读 CSV 大词库）。"""
    if not hasattr(page, 'search_results'):
        return
    q = (page.search_field.value or "").strip()
    scope = page.scope_dropdown.value
    results_list = page.search_results
    results_list.controls.clear()

    if not q:
        results_list.update()
        return

    book = None if scope == "全部词本" else get_current_book()
    if scope != "全部词本" and not book:
        results_list.controls.append(
            ft.Text("尚未设置当前词库，请先在下方词本中点「设为当前」", size=13, color=ft.Colors.GREY))
        results_list.update()
        return

    results = wb.search_words(q, book)
    if not results:
        results_list.controls.append(ft.Text("无匹配结果", size=13, color=ft.Colors.GREY))
    else:
        for r in results:
            word_row = ft.Row(
                [ft.Text(r['word'], size=15, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)],
                spacing=8,
            )
            if book is None:
                word_row.controls.append(ft.Text(f"「{r['book_name']}」", size=11, color=ft.Colors.GREY))
            results_list.controls.append(
                glass(
                    ft.Column(
                        [word_row, ft.Text(r['trans'] or "", size=13, color=SUB_TEXT_COLOR)],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                    ),
                    padding=10,
                    radius=10,
                )
            )
        if len(results) >= 100:
            results_list.controls.append(
                ft.Text("结果过多已截断，请继续输入以缩小范围", size=12, color=ft.Colors.GREY))
    results_list.update()


def build_wordbook_page(page: ft.Page) -> ft.Control:
    builtin_tiles = ft.Column(spacing=10)
    custom_tiles = ft.Column(spacing=10)
    page.builtin_tiles = builtin_tiles
    page.custom_tiles = custom_tiles

    builtin_section = _section(ft.Icons.BOOKMARK, "内置词本（只读）", builtin_tiles, initially_expanded=False)
    custom_section = _section(ft.Icons.CREATE_NEW_FOLDER, "我的自定义词本", custom_tiles, initially_expanded=True)
    page.builtin_section = builtin_section
    page.custom_section = custom_section

    # FilePicker（仅词库页复用一次，路由切换后 overlay 仍保留）
    if not getattr(page, '_wordbook_file_picker', None):
        file_picker = ft.FilePicker(on_result=lambda e: on_file_picked(e, page))
        page.overlay.append(file_picker)
        page._wordbook_file_picker = file_picker
    else:
        file_picker = page._wordbook_file_picker

    back_btn = glass_button("返回首页", lambda _: page.go("/"))
    batch_btn = glass_button("批量识别", lambda _: page.go("/batch"), icon=ft.Icons.AUTO_AWESOME)
    new_btn = glass_button("新建词本", lambda _: open_new_dialog(page), icon=ft.Icons.ADD)
    import_btn = glass_button("导入 CSV", lambda _: file_picker.pick_files(allowed_extensions=["csv"], allow_multiple=False))

    # 词本内单词检索（与「批量识别/添加单词」入口互相独立，仅检索已加载词本）
    search_field = ft.TextField(
        label="检索单词（输入单词或释义）",
        prefix_icon=ft.Icons.SEARCH,
        on_change=lambda e: _run_search(page),
    )
    scope_dropdown = ft.Dropdown(
        label="检索范围",
        value="全部词本",
        options=[
            ft.dropdown.Option(key="全部词本", text="全部词本"),
            ft.dropdown.Option(key="当前选中词本", text="当前选中词本"),
        ],
        on_change=lambda e: _run_search(page),
    )
    search_results = ft.Column(spacing=6)
    page.search_field = search_field
    page.scope_dropdown = scope_dropdown
    page.search_results = search_results

    return page_shell(
        page,
        ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        [back_btn, ft.Text("词库管理", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row([batch_btn, new_btn, import_btn], spacing=8, wrap=True),
                    search_field,
                    scope_dropdown,
                    search_results,
                    builtin_section,
                    custom_section,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    )


def refresh_wordbook_page(page: ft.Page):
    """刷新两段抽屉的列表与计数。"""
    if not hasattr(page, 'builtin_tiles') or not hasattr(page, 'custom_tiles'):
        return

    books = wb.list_wordbooks()
    builtin = [b for b in books if b[2]]
    custom = [b for b in books if not b[2]]

    page.builtin_tiles.controls = [
        _book_tile(page, name, remark, cnt, True) for name, remark, _b, cnt in builtin
    ]
    page.builtin_section.subtitle = ft.Text(
        f"{len(builtin)} 本 · {sum(c for _, _, _, c in builtin)} 词",
        size=12, color=ft.Colors.GREY,
    )

    page.custom_tiles.controls = [
        _book_tile(page, name, remark, cnt, False) for name, remark, _b, cnt in custom
    ]
    if not custom:
        page.custom_tiles.controls.append(
            ft.Text("还没有自定义词本，点击上方「新建词本」或「导入 CSV」创建", size=13, color=ft.Colors.GREY)
        )
    page.custom_section.subtitle = ft.Text(
        f"{len(custom)} 本 · {sum(c for _, _, _, c in custom)} 词",
        size=12, color=ft.Colors.GREY,
    )

    page.update()


def set_current_book_and_refresh(page, book_name):
    set_current_book(book_name)
    refresh_wordbook_page(page)
    _snack(page, f"已将「{book_name}」设为当前词库", ft.Colors.GREEN)


def open_book_detail(page, book_name):
    page.current_view_book = book_name
    page.go("/book_detail")


# ---------------- 对话框：新建 / 重命名 / 备注 / 删除 ----------------

def open_new_dialog(page):
    name_field = ft.TextField(label="词本名称", autofocus=True)
    remark_field = ft.TextField(label="备注（可选）")

    def _create(_):
        name = (name_field.value or "").strip()
        if not name:
            _snack(page, "创建失败：词本名称不能为空", ft.Colors.RED)
            return
        if wb.create_wordbook(name, (remark_field.value or "").strip()):
            _close(page, page._active_dialog)
            refresh_wordbook_page(page)
            _snack(page, f"已创建词本「{name}」", ft.Colors.GREEN)
        else:
            _snack(page, "创建失败：名称已存在", ft.Colors.RED)

    _dialog(page, "新建自定义词本", ft.Column([name_field, remark_field]), "创建", _create)


def open_rename_dialog(page, name):
    field = ft.TextField(label="新名称", value=name, autofocus=True)

    def _do(_):
        new = (field.value or "").strip()
        if not new:
            _snack(page, "重命名失败：名称不能为空", ft.Colors.RED)
            return
        if wb.rename_wordbook(name, new):
            _close(page, page._active_dialog)
            refresh_wordbook_page(page)
            _snack(page, f"已重命名「{name}」→「{new}」", ft.Colors.GREEN)
        else:
            _snack(page, "重命名失败：名称已存在", ft.Colors.RED)

    _dialog(page, "重命名词本", field, "保存", _do)


def open_remark_dialog(page, name, remark):
    field = ft.TextField(label="备注", value=remark or "", multiline=True, min_lines=2, max_lines=4)

    def _do(_):
        wb.set_remark(name, (field.value or "").strip())
        _close(page, page._active_dialog)
        refresh_wordbook_page(page)
        _snack(page, "备注已保存", ft.Colors.GREEN)

    _dialog(page, f"编辑「{name}」备注", field, "保存", _do)


def open_delete_dialog(page, name):
    def _do(_):
        wb.delete_wordbook(name)
        _close(page, page._active_dialog)
        refresh_wordbook_page(page)
        _snack(page, f"已删除词本「{name}」", ft.Colors.GREEN)

    _dialog(page, "删除词本", ft.Text(f"确定删除「{name}」及其全部单词吗？此操作不可撤销。"), "删除", _do, danger=True)


def _dialog(page, title, content, confirm_text, on_confirm, danger=False):
    dialog = ft.AlertDialog(
        title=ft.Text(title),
        content=content if isinstance(content, ft.Control) else ft.Column([content]),
        actions=[
            ft.TextButton("取消", on_click=lambda _: _close(page, dialog)),
            ft.ElevatedButton(
                confirm_text,
                on_click=on_confirm,
                bgcolor=ft.Colors.RED_400 if danger else None,
                color=ft.Colors.WHITE if danger else None,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page._active_dialog = dialog
    page.open(dialog)


def _close(page, dialog):
    page.close(dialog)


def _snack(page, msg, color):
    page.open(ft.SnackBar(ft.Text(msg), bgcolor=color))


# ---------------- CSV 导入 ----------------

def on_file_picked(e, page):
    if not e.files:
        return
    file_path = e.files[0].path
    name_field = ft.TextField(label="导入到词本名称", value="我的词本", autofocus=True)

    def _do(_):
        name = (name_field.value or "").strip()
        if not name:
            _snack(page, "导入失败：词本名称不能为空", ft.Colors.RED)
            return
        try:
            count = wb.import_csv_to_book(file_path, name)
            _close(page, page._active_dialog)
            refresh_wordbook_page(page)
            _snack(page, f"成功导入 {count} 个单词到「{name}」", ft.Colors.GREEN)
        except Exception as ex:
            _snack(page, f"导入失败: {ex}", ft.Colors.RED)

    _dialog(page, "导入 CSV",
            ft.Column([name_field, ft.Text(f"文件: {file_path}", size=12, color=ft.Colors.GREY)]), "导入", _do)
