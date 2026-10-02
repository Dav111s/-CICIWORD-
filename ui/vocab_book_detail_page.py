# ui/vocab_book_detail_page.py
"""词本详情页：按词本类型区分只读与可移除。

- 用户自定义词本（is_builtin=0）：每条右侧显示红色【移除】，仅删除该词本内该条记录，
  不删单词本体，其他词本同名单词不受影响。
- 系统核心词库（is_builtin=1）：完全只读，无移除按钮、不可编辑，仅浏览/背诵。
"""
import flet as ft

from data.db import get_words_by_book
from data import wordbooks as wb
from ui.theme import glass, page_shell, TEXT_COLOR, SUB_TEXT_COLOR


def _book_type(name: str) -> str:
    """返回词本类型 'user_custom' | 'system_core'；未知词本默认按自定义处理。"""
    if name:
        for b_name, _remark, is_builtin, _cnt in wb.list_wordbooks():
            if b_name == name:
                return "system_core" if is_builtin else "user_custom"
    return "user_custom"


def _build_items(page: ft.Page, words=None):
    """构建词本内单词列表。自定义词本带【移除】按钮，系统词库只读。"""
    book_name = getattr(page, 'current_view_book', None)
    if words is None:
        words = get_words_by_book(book_name) if book_name else []
    is_custom = _book_type(book_name) == "user_custom"

    items = []
    for w in words:
        example = (w.get('example') or '').strip()
        word_row = ft.Row(
            [
                ft.Text(w['word'], size=18, weight=ft.FontWeight.BOLD, color=TEXT_COLOR, expand=True),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        if is_custom:
            # 仅自定义词本显示移除按钮
            word_row.controls.append(
                ft.TextButton(
                    "移除", icon=ft.Icons.DELETE,
                    style=ft.ButtonStyle(color=ft.Colors.RED_400),
                    on_click=lambda e, wid=w['id']: _confirm_remove(page, wid),
                )
            )
        items.append(
            glass(
                ft.Column(
                    [
                        word_row,
                        ft.Text(w['trans'] or '', size=14, color=SUB_TEXT_COLOR),
                        ft.Text(f"例句：{example}", size=13, italic=True, color=ft.Colors.GREY) if example else ft.Text(""),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                radius=14, padding=12,
            )
        )

    if not items:
        items.append(ft.Text("该词本暂无单词", size=16, color=ft.Colors.GREY))
    return items


def _confirm_remove(page: ft.Page, word_id: int):
    """确认弹窗：仅从当前自定义词本移除该单词，不影响其他词本。"""

    def _do(_):
        wb.delete_word(word_id)  # 仅删该词本内该条记录（is_builtin=0 才删，系统词库受保护）
        page.close(dialog)
        # 刷新列表 + Toast 提示
        page.detail_list_view.controls = _build_items(page)
        page.detail_list_view.update()
        page.open(ft.SnackBar(ft.Text("已移除该单词"), bgcolor=ft.Colors.GREEN))

    dialog = ft.AlertDialog(
        title=ft.Text("移除单词"),
        content=ft.Text("确定从该自定义词本移除此单词？该操作不会影响其他词本。"),
        actions=[
            ft.TextButton("取消", on_click=lambda e: page.close(dialog)),
            ft.ElevatedButton("移除", on_click=_do, bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.open(dialog)


def build_vocab_book_detail_page(page: ft.Page) -> ft.Control:
    book_name = getattr(page, 'current_view_book', None)
    words = get_words_by_book(book_name) if book_name else []
    book_type = _book_type(book_name) if book_name else "system_core"
    type_label = "自定义词本" if book_type == "user_custom" else "系统核心词库"

    list_view = ft.ListView(controls=_build_items(page, words), expand=True, spacing=10)
    page.detail_list_view = list_view  # 供移除后刷新

    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回词库", on_click=lambda e: page.go("/wordbook"))
    title_text = ft.Text(book_name or "词本详情", size=20, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
    sub_text = ft.Text(f"{type_label} · {len(words)} 个单词", size=13, color=ft.Colors.GREY)

    return page_shell(
        page,
        ft.Column(
            [
                ft.Container(
                    content=ft.Row([back_btn, title_text], alignment=ft.MainAxisAlignment.START),
                    padding=ft.padding.symmetric(horizontal=8, vertical=6),
                ),
                ft.Container(content=sub_text, padding=ft.padding.symmetric(horizontal=8)),
                ft.Container(content=list_view, expand=True, padding=ft.padding.symmetric(horizontal=16)),
            ],
            expand=True,
            spacing=8,
        ),
    )
