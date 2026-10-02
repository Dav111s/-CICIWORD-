# ui/favorites_page.py
"""收藏集页面：读取已收藏单词，毛玻璃卡片滚动展示，可查看释义、移除收藏（仅取消收藏，不删词条）。"""
import flet as ft

from data.db import get_favorite_words, set_word_favorite
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR


def _build_items(page: ft.Page):
    words = get_favorite_words()
    items = []
    for w in words:
        example = (w.get('example') or '').strip()
        items.append(
            glass(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(w['word'], size=20, weight=ft.FontWeight.BOLD, color=TEXT_COLOR, expand=True),
                                ft.TextButton(
                                    "移除", icon=ft.Icons.DELETE,
                                    on_click=lambda e, wid=w['id']: _remove_favorite(page, wid),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Text(w['trans'] or '', size=15, color=SUB_TEXT_COLOR),
                        ft.Text(f"例句：{example}", size=13, italic=True, color=ft.Colors.GREY) if example else ft.Text(""),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                radius=14, padding=14,
            )
        )

    if not items:
        items.append(ft.Text("暂无收藏单词", size=15, color=ft.Colors.GREY))
    return items


def _remove_favorite(page: ft.Page, word_id: int):
    """仅从收藏集移除（favorite=0），不删除词库原始词条。"""
    set_word_favorite(word_id, 0)
    page.favorites_list.controls = _build_items(page)
    page.favorites_list.update()
    page.open(ft.SnackBar(ft.Text("已从收藏集移除"), bgcolor=ft.Colors.GREEN))


def build_favorites_page(page: ft.Page) -> ft.Control:
    list_view = ft.ListView(controls=_build_items(page), expand=True, spacing=12)
    page.favorites_list = list_view
    back_btn = glass_button("返回首页", lambda _: page.go("/"))

    return page_shell(
        page,
        ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [back_btn, ft.Text("收藏集", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    list_view,
                ],
                expand=True,
                spacing=16,
            ),
            expand=True,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    )
