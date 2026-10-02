# ui/home_page.py
"""首页：低饱和渐变背景 + 两个大毛玻璃按钮 + 毛玻璃底部导航栏。"""
import flet as ft

from config import get_current_book, get_bg_gradient
from data import statistics as st
from ui.theme import get_gradient, glass, TEXT_COLOR, SUB_TEXT_COLOR


def build_home_page(page: ft.Page) -> ft.Control:
    book = get_current_book()
    learn_count = st.get_learn_pending_count(book)
    review_count = st.get_review_due_count(book)
    book_display = f"当前词库：{book}" if book else "当前词库：全部（未设置）"

    def _big_btn(title, subtitle, route, col):
        return glass(
            ft.Column(
                [
                    ft.Text(title, size=28, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                    ft.Text(subtitle, size=14, color=SUB_TEXT_COLOR),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            opacity=0.26,
            radius=22,
            height=150,
            ink=True,
            col=col,
            on_click=lambda e: page.go(route),
        )

    main_content = ft.Column(
        [
            ft.Text("萃词 CICIWORD", size=24, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
            ft.Text(book_display, size=14, color=SUB_TEXT_COLOR),
            ft.Container(height=24),
            # 两个入口按钮随窗口宽度自适应（窄屏整行、宽屏并排收窄），不再固定 300 宽
            ft.ResponsiveRow(
                [
                    _big_btn("Learn", f"待学习 {learn_count} 个新词", "/learn", {"xs": 12, "sm": 10, "md": 6, "lg": 4}),
                    _big_btn("Review", f"待复习 {review_count} 个单词", "/review", {"xs": 12, "sm": 10, "md": 6, "lg": 4}),
                ],
                spacing=16,
                run_spacing=16,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=16,
    )

    nav = ft.NavigationBar(
        bgcolor=ft.Colors.with_opacity(0.30, ft.Colors.WHITE),
        indicator_color=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
        selected_index=0,
        on_change=lambda e: page.go(["/", "/wordbook", "/stats", "/settings"][e.control.selected_index]),
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME, label="首页"),
            ft.NavigationBarDestination(icon=ft.Icons.BOOK, label="词库"),
            ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART, label="统计"),
            ft.NavigationBarDestination(icon=ft.Icons.SETTINGS, label="设置"),
        ],
    )

    # 右上角星星：打开收藏集
    star_btn = ft.IconButton(
        icon=ft.Icons.STAR,
        icon_color=ft.Colors.AMBER,
        icon_size=26,
        tooltip="收藏集",
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
            shape=ft.CircleBorder(),
            side=ft.BorderSide(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
            overlay_color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
        ),
        on_click=lambda e: page.go("/favorites"),
    )

    main_with_star = ft.Stack(
        [
            ft.Container(expand=True, content=main_content, alignment=ft.alignment.center),
            ft.Container(content=star_btn, padding=ft.padding.only(top=8, right=8)),
        ],
        expand=True,
        fit=ft.StackFit.LOOSE,
        alignment=ft.alignment.top_right,
    )

    return ft.Container(
        expand=True,
        gradient=get_gradient(get_bg_gradient()),
        content=ft.Column(
            [
                main_with_star,
                nav,
            ],
            spacing=0,
        ),
    )
