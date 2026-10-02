# ui/settings_page.py
"""设置页：每组学习词数、拼写开关、6 种主题配色选择。"""
import flet as ft

from config import (
    get_study_group_size,
    set_study_group_size,
    is_spelling_test_enabled,
    set_spelling_test_enabled,
    get_bg_gradient,
    set_bg_gradient,
)
from ui.theme import (
    glass_button,
    get_gradient,
    get_theme_name,
    THEMES,
    TEXT_COLOR,
)


def build_settings_page(page: ft.Page) -> ft.Control:
    status_text = ft.Text("", size=13, color=ft.Colors.GREEN)
    back_btn = glass_button("返回首页", lambda _: page.go("/"))

    group_field = ft.TextField(
        label="每组学习词数（5~50）",
        value=str(get_study_group_size()),
        keyboard_type=ft.KeyboardType.NUMBER,
        on_change=lambda e: _on_group_change(page, e, group_field, status_text),
    )
    spelling_switch = ft.Switch(
        label="完成一组后开启拼写练习",
        value=is_spelling_test_enabled(),
        on_change=lambda e: _on_spelling_change(page, e, status_text),
    )

    shell_ref = [None]

    def _on_theme_change(page, e, status):
        idx = int(e.control.value or 0)
        set_bg_gradient(idx)
        if shell_ref[0] is not None:
            shell_ref[0].gradient = get_gradient(idx)
        status.value = f"已切换：{get_theme_name(idx)}"
        status.color = ft.Colors.GREEN
        page.update()

    theme_group = ft.RadioGroup(
        content=ft.Column(
            [ft.Radio(value=str(i), label=t[0]) for i, t in enumerate(THEMES)],
            spacing=8,
        ),
        value=str(get_bg_gradient()),
        on_change=lambda e: _on_theme_change(page, e, status_text),
    )

    body = ft.Container(
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Row([back_btn], alignment=ft.MainAxisAlignment.START),
                ft.Text("设置", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                group_field,
                spelling_switch,
                ft.Text("主题配色", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                theme_group,
                status_text,
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=16,
        ),
        expand=True,
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
    )

    shell = ft.Container(expand=True, gradient=get_gradient(get_bg_gradient()), content=body)
    shell_ref[0] = shell
    return shell


def _on_group_change(page, e, field, status):
    try:
        n = int(e.control.value or 10)
    except ValueError:
        return
    n = max(5, min(50, n))
    set_study_group_size(n)
    field.value = str(n)
    status.value = "已保存"
    status.color = ft.Colors.GREEN
    page.update()


def _on_spelling_change(page, e, status):
    set_spelling_test_enabled(bool(e.control.value))
    status.value = "已保存"
    status.color = ft.Colors.GREEN
    page.update()
