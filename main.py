# main.py
"""程序入口：Flet 页面路由控制。"""
import flet as ft

from data.db import init_db

from data import wordbooks
from ui.theme import FONT_FAMILY
from ui.home_page import build_home_page
from ui.wordbook_page import build_wordbook_page, refresh_wordbook_page
from ui.review_page import build_review_page, load_review_data
from ui.learn_page import build_learn_page, load_learn_data
from ui.group_summary_page import build_group_summary_page
from ui.stats_finish_page import build_stats_finish_page
from ui.spelling_page import build_spelling_page
from ui.vocab_book_detail_page import build_vocab_book_detail_page
from ui.favorites_page import build_favorites_page
from ui.settings_page import build_settings_page
from ui.stats_page import build_stats_page, refresh_stats_page
from ui.batch_page import build_batch_page


def main(page: ft.Page):
    page.title = "萃词 ciciword"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    # 页面底色：底部按钮容器直接复用该颜色，消除色块分割
    page.bgcolor = ft.Colors.PURPLE_50
    # 全局字体体系（Segoe UI / SF / 系统无衬线）
    page.theme = ft.Theme(font_family=FONT_FAMILY)

    # 9:16 手机竖屏基准比例，窗口可放大缩小，内部布局自适应（expand/百分比）
    try:
        page.window.width = 360
        page.window.height = 640
        page.window.min_width = 320
        page.window.min_height = 480
    except Exception:
        pass

    init_db()
    # 首次运行自动生成内置词本（考研/四级/六级/高考/中考）+ 导入单词
    wordbooks.init_wordbooks()

    # 预渲染根容器：只添加一次，切换页面时仅替换 content，避免整体销毁重建导致黑屏闪烁
    root = ft.Container(expand=True, bgcolor=ft.Colors.PURPLE_50)
    page.add(root)

    def route_change(route):
        # 只替换根容器内容，不做 page.clean() 整体销毁
        if page.route == "/":
            root.content = build_home_page(page)
        elif page.route == "/wordbook":
            root.content = build_wordbook_page(page)
            refresh_wordbook_page(page)
        elif page.route == "/batch":
            root.content = build_batch_page(page)
        elif page.route == "/book_detail":
            root.content = build_vocab_book_detail_page(page)
        elif page.route == "/favorites":
            root.content = build_favorites_page(page)
        elif page.route == "/learn":
            root.content = build_learn_page(page)
            load_learn_data(page)
        elif page.route == "/review":
            root.content = build_review_page(page)
            load_review_data(page)
        elif page.route == "/spelling":
            root.content = build_spelling_page(page)
        elif page.route == "/summary":
            root.content = build_group_summary_page(page)
        elif page.route == "/learn_stats":
            root.content = build_stats_finish_page(page)
        elif page.route == "/settings":
            root.content = build_settings_page(page)
        elif page.route == "/stats":
            root.content = build_stats_page(page)
            # 进入统计主页时重读数据库：学完/复习完一轮返回即可看到最新今日统计，无需重启
            refresh_stats_page(page)
        page.update()

    page.on_route_change = route_change
    page.go("/")


if __name__ == "__main__":
    ft.app(target=main,assets_dir="assets")
