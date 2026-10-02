# ui/spelling_page.py
"""拼写练习页：展示中文释义，输入英文单词校验。

拼写对错仅作为巩固练习，写入 test_records，不影响艾宾浩斯记忆关卡数据。
提供【跳过拼写】按钮，可直接结束本组流程。
"""
import flet as ft
from datetime import datetime

from data.db import insert_test_record
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR


def build_spelling_page(page: ft.Page) -> ft.Control:
    state = getattr(page, 'spelling_state', None) or {}
    words = state.get('words', []) or []
    return_route = state.get('return_route', '/')

    prog = {'index': 0, 'correct': 0, 'answered': 0}

    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回", on_click=lambda e: page.go(return_route))
    skip_btn = glass_button("跳过拼写", lambda e: page.go(return_route))
    title_text = ft.Text("拼写练习", size=20, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
    progress_text = ft.Text("", size=13, color=ft.Colors.GREY)

    trans_text = ft.Text("", size=24, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    trans_card = glass(
        ft.Column([trans_text], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        radius=18, padding=26,
    )

    input_field = ft.TextField(
        label="输入英文单词",
        autofocus=True,
        on_submit=lambda e: _submit(page),
    )
    result_text = ft.Text("", size=15)

    submit_btn = glass_button("提交", lambda e: _submit(page), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)

    def _submit(page):
        if prog['index'] >= len(words):
            return
        item = words[prog['index']]
        got = (input_field.value or '').strip().lower()
        correct = (got == item['word'].strip().lower())
        insert_test_record(item['id'], correct, datetime.now().strftime('%Y-%m-%d'))
        prog['answered'] += 1
        if correct:
            prog['correct'] += 1
            result_text.value = "✓ 正确"
            result_text.color = ft.Colors.GREEN
        else:
            result_text.value = f"✗ 错误，正确答案：{item['word']}"
            result_text.color = ft.Colors.RED
        prog['index'] += 1
        input_field.value = ""
        _next(page)

    def _next(page):
        if prog['index'] >= len(words):
            _finish(page)
        else:
            trans_text.value = words[prog['index']]['trans']
            progress_text.value = f"第 {prog['index'] + 1}/{len(words)} 个"
            result_text.value = ""
            result_text.color = None
        page.update()

    def _finish(page):
        acc = round(prog['correct'] / prog['answered'] * 100, 1) if prog['answered'] else 0
        trans_text.value = "本组拼写完成"
        input_field.visible = False
        submit_btn.visible = False
        skip_btn.text = "完成"
        result_text.value = f"正确 {prog['correct']}/{prog['answered']}（{acc}%）"
        result_text.color = ft.Colors.GREEN
        page.update()

    if not words:
        return ft.Column(
            [
                ft.Text("本组无可拼写单词", size=18),
                ft.ElevatedButton("返回", on_click=lambda e: page.go(return_route)),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    _next(page)

    layout = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Row(
                [back_btn, ft.Container(title_text, expand=True, alignment=ft.alignment.center), skip_btn],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            progress_text,
            trans_card,
            input_field,
            result_text,
        ],
        spacing=16,
    )

    bottom_bar = ft.Container(
        content=ft.Row([submit_btn], alignment=ft.MainAxisAlignment.CENTER),
        padding=ft.padding.symmetric(vertical=12),
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
