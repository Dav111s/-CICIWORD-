# ui/theme.py
"""主题：萃词 Lexera 统一视觉体系（多巴胺低饱和渐变 + 毛玻璃 Glass-Morphism）。

- 字体：Windows 优先 Segoe UI，macOS 回退系统 San Francisco，兜底无衬线。
- 背景：6 种可切换的低饱和渐变主题，所有页面统一跟随。
- 毛玻璃：半透明 bgcolor 透出底色 + 柔光描边 + 柔和圆角 + 低透明度阴影。
  说明：flet 0.28.3 无 image_filter/BackdropFilter，用半透明 bgcolor 实现磨砂；
       Container.blur 序列化异常已弃用。
"""
import platform

import flet as ft

# 全局字体：Windows 用 Segoe UI；macOS/其它回退系统默认无衬线（SF）
FONT_FAMILY = "Segoe UI" if platform.system() == "Windows" else None

# 深色文字（浅色渐变底上保持清晰）
TEXT_COLOR = ft.Colors.PURPLE_900
SUB_TEXT_COLOR = ft.Colors.PURPLE_700

# 6 种多巴胺渐变主题（克制、低饱和、高级）：(名称, from_color, to_color)
THEMES = [
    ("莓果紫粉", "#F7C6D9", "#D8A8FF"),
    ("薄荷青柠", "#DFF8E3", "#A7E9D3"),
    ("天空海盐", "#DDEAF7", "#A4CFF5"),
    ("奶油杏橙", "#FFE8D6", "#FFB38A"),
    ("葡萄果冻", "#E8D5FF", "#B88DFF"),
    ("蓝紫梦境", "#E0E7FF", "#A78BFA"),
]


def get_theme_count() -> int:
    return len(THEMES)


def get_theme_name(index: int) -> str:
    return THEMES[index % len(THEMES)][0]


def get_gradient(index: int = 0) -> ft.LinearGradient:
    idx = max(0, min(len(THEMES) - 1, int(index)))
    _, c_from, c_to = THEMES[idx]
    return ft.LinearGradient(
        begin=ft.alignment.top_left,
        end=ft.alignment.bottom_right,
        colors=[c_from, c_to],
    )


def page_shell(page: ft.Page, body: ft.Control) -> ft.Container:
    """统一渐变背景外壳：所有页面背景跟随当前主题渐变。"""
    from config import get_bg_gradient
    return ft.Container(
        expand=True,
        gradient=get_gradient(get_bg_gradient()),
        content=body,
    )


def glass(
    content: ft.Control,
    tint=ft.Colors.WHITE,
    opacity: float = 0.18,
    radius: float = 18,
    padding=14,
    border_opacity: float = 0.06,
    on_click=None,
    **kwargs,
) -> ft.Container:
    """iOS 毛玻璃卡片：半透明 bgcolor 透出底色 + 柔和描边 + 圆角 + 低透明度阴影。"""
    return ft.Container(
        content=content,
        bgcolor=ft.Colors.with_opacity(opacity, tint),
        border=ft.border.all(1, ft.Colors.with_opacity(border_opacity, ft.Colors.WHITE)),
        border_radius=radius,
        padding=padding,
        shadow=ft.BoxShadow(
            blur_radius=20,
            spread_radius=1,
            color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
            offset=ft.Offset(0, 6),
        ),
        on_click=on_click,
        **kwargs,
    )


def glass_button(text, on_click, tint=ft.Colors.WHITE, opacity=0.18, text_color=None, icon=None, height=48):
    """毛玻璃按钮：半透明底 + 柔光描边 + 低阴影，无实色填充，手机友好高度 48-56。"""
    return ft.ElevatedButton(
        text,
        on_click=on_click,
        icon=icon,
        height=height,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.with_opacity(opacity, tint),
            color=text_color or TEXT_COLOR,
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=14),
            side=ft.BorderSide(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
            overlay_color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
            padding=ft.padding.symmetric(horizontal=20, vertical=6),
        ),
    )
