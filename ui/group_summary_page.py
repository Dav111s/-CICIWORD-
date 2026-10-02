# ui/group_summary_page.py
"""本组学习小结页。

布局：
- 顶部：标题「本组学习小结」+ 统计「共 N 个单词」。
- 中间：可滚动 ListView，每条卡片 Row 布局 —— 左侧英文+释义（占大部分宽度），
  右侧固定靠右显示复习天数标签（`3天后复习` / `今日复习`）。
- 底部：固定栏【再学一组】【休息一下】，不随列表滚动。

数据与持久化：
- 每个单词含 spaced-repetition 字段 `next_review_days`（距离下次复习天数）。
- 优先读取内存中本次刚学完的一组（learn_state['completed']），并写入本地 JSON；
  Activity 重建（内存丢失）时从 JSON 恢复。
"""
import json
import os

import flet as ft

from paths import get_data_dir
from ui.theme import glass_button, page_shell

_SUMMARY_FILE = "summary_state.json"


def _summary_path() -> str:
    return str(get_data_dir() / _SUMMARY_FILE)


def _load_summary():
    """从本地 JSON 恢复小结数据；缺失/损坏返回空列表。"""
    try:
        if os.path.exists(_summary_path()):
            with open(_summary_path(), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_summary(data):
    """把小结数据（含 next_review_days）写入本地 JSON；失败静默。"""
    try:
        with open(_summary_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _get_summary_data(page: ft.Page):
    """取本组小结数据：优先内存（刚学完），回退本地 JSON（Activity 重建）。

    统一归一化为 [{'word','trans','next_review_days'}]。
    """
    if hasattr(page, 'learn_state') and page.learn_state.get('completed'):
        raw = page.learn_state['completed']
        data = [{
            'word': it.get('word', ''),
            'trans': it.get('trans', ''),
            # 兼容 interval / next_review_days 两种字段名
            'next_review_days': int(it.get('interval') or it.get('next_review_days') or 0),
        } for it in raw]
        _save_summary(data)  # 持久化，供 Activity 重建恢复
        return data
    # 回退：拼写测试路径（spelling_state.words，可能不带 interval，按 0 处理）
    if hasattr(page, 'spelling_state') and page.spelling_state.get('words'):
        raw = page.spelling_state['words']
        data = [{
            'word': it.get('word', ''),
            'trans': it.get('trans', ''),
            'next_review_days': int(it.get('interval') or it.get('next_review_days') or 0),
        } for it in raw]
        _save_summary(data)
        return data
    return _load_summary()


def _day_label(days: int) -> str:
    """复习天数 -> 右侧标签文本。0 显示「今日复习」，>0 显示「N天后复习」。"""
    if int(days or 0) <= 0:
        return "今日复习"
    return f"{int(days)}天后复习"


def _build_items(data):
    """构建单词条目卡片（Row：左侧英文+释义，右侧复习天数标签）。高对比度配色。"""
    items = []
    for it in data:
        days = int(it.get('next_review_days') or 0)
        label = _day_label(days)

        items.append(
            # 淡粉卡片底 + 深色文字，强光下清晰可读
            ft.Container(
                content=ft.Row(
                    [
                        # 左侧：英文 + 释义（占大部分宽度）
                        ft.Column(
                            [
                                ft.Text(it['word'], size=20, weight=ft.FontWeight.BOLD, color="#222222"),
                                ft.Text(it.get('trans', ''), size=15, color="#444444"),
                            ],
                            spacing=2,
                            expand=True,
                            horizontal_alignment=ft.CrossAxisAlignment.START,
                        ),
                        # 右侧：复习天数标签（固定靠右，深紫色）
                        ft.Text(label, size=14, color="#702090"),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor="#f3d7f0",
                border_radius=12,
                padding=12,
            )
        )

    if not items:
        items.append(ft.Text("本组没有已学完的单词", size=16, color="#666666"))
    return items


def build_group_summary_page(page: ft.Page) -> ft.Control:
    data = _get_summary_data(page)

    # 中间可滚动列表
    list_view = ft.ListView(controls=_build_items(data), expand=True, spacing=10)

    # 底部固定栏（不随列表滚动）
    bottom_bar = ft.Container(
        content=ft.Row(
            [
                glass_button("再学一组", lambda e: page.go("/learn"),
                             tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900),
                glass_button("休息一下", lambda e: page.go("/wordbook")),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
        ),
        padding=ft.padding.symmetric(vertical=12),
    )

    # 顶部：标题 + 统计
    header = ft.Column(
        [
            ft.Text("本组学习小结", size=24, weight=ft.FontWeight.BOLD, color="#6622aa"),
            ft.Text(f"共 {len(data)} 个单词", size=14, color="#666666"),
        ],
        spacing=4,
        horizontal_alignment=ft.CrossAxisAlignment.START,
    )

    return page_shell(
        page,
        ft.Column(
            [
                ft.Container(content=header, padding=ft.padding.symmetric(horizontal=16, vertical=12)),
                ft.Container(content=list_view, expand=True, padding=ft.padding.symmetric(horizontal=16)),
                bottom_bar,
            ],
            spacing=0,
            expand=True,
        ),
    )
