# ui/stats_finish_page.py
"""学习完成统计页：今日学习数量、今日总学习时长（毛玻璃统计卡）。"""
import flet as ft

from config import get_current_book, get_today_study_duration
from data import statistics as st
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR


def _fmt_duration(seconds) -> str:
    seconds = int(seconds or 0)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} 小时 {m} 分"
    if m:
        return f"{m} 分 {s} 秒"
    return f"{s} 秒"


def build_stats_finish_page(page: ft.Page) -> ft.Control:
    book = get_current_book()
    today_learned = st.get_today_learned_count(book)
    duration = get_today_study_duration()

    def _card(title, value):
        return glass(
            ft.Column(
                [
                    ft.Text(title, size=15, color=ft.Colors.GREY),
                    ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            height=120, radius=18,
        )

    bottom_bar = ft.Container(
        content=ft.Row(
            [glass_button("完成，回到首页", lambda e: page.go("/"), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        padding=ft.padding.symmetric(vertical=12),
    )

    layout = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Text("学习完成统计", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
            _card("今日学习单词", f"{today_learned} 个"),
            _card("今日总学习时长", _fmt_duration(duration)),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=20,
    )

    return page_shell(
        page,
        ft.Column(
            [
                ft.Container(content=layout, expand=True, padding=ft.padding.symmetric(horizontal=16, vertical=12)),
                bottom_bar,
            ],
            spacing=0,
            expand=True,
        ),
    )
