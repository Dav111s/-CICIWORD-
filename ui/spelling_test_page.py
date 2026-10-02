# ui/spelling_test_page.py
"""拼写测试：展示中文释义，输入英文单词，回车/按钮提交，可跳过。"""
import flet as ft
from datetime import datetime

from data.db import insert_test_record


def build_spelling_test_page(page: ft.Page) -> ft.Control:
    learned = page.learn_state.get('learned', []) if hasattr(page, 'learn_state') else []
    if not learned:
        return ft.Column(
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text("没有可测试的单词", size=20),
                ft.ElevatedButton("返回首页", on_click=lambda _: page.go("/")),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    page.spelling_state = {
        'items': list(learned),
        'index': 0,
        'correct': 0,
        'answered': 0,
    }

    trans_text = ft.Text("", size=26, text_align=ft.TextAlign.CENTER)
    input_field = ft.TextField(
        label="输入英文单词",
        width=300,
        autofocus=True,
        on_submit=lambda e: _submit(page),
    )
    result_text = ft.Text("", size=16)
    status_text = ft.Text("", size=18)
    submit_btn = ft.ElevatedButton("提交", on_click=lambda e: _submit(page))
    skip_btn = ft.TextButton("跳过", on_click=lambda e: _skip(page))
    back_btn = ft.ElevatedButton("返回首页", on_click=lambda _: page.go("/"))

    def _submit(page):
        _check(page, input_field.value)

    def _check(page, value):
        s = page.spelling_state
        if s['index'] >= len(s['items']):
            return
        item = s['items'][s['index']]
        got = (value or '').strip().lower()
        correct = (got == item['word'].strip().lower())
        insert_test_record(item['id'], correct, datetime.now().strftime("%Y-%m-%d"))
        s['answered'] += 1
        if correct:
            s['correct'] += 1
            result_text.value = "✔ 正确"
            result_text.color = ft.Colors.GREEN
        else:
            result_text.value = f"✘ 错误，正确答案：{item['word']}"
            result_text.color = ft.Colors.RED
        s['index'] += 1
        input_field.value = ""
        _next(page)

    def _skip(page):
        s = page.spelling_state
        if s['index'] >= len(s['items']):
            return
        item = s['items'][s['index']]
        insert_test_record(item['id'], False, datetime.now().strftime("%Y-%m-%d"))
        s['answered'] += 1
        result_text.value = f"已跳过，正确答案：{item['word']}"
        result_text.color = ft.Colors.ORANGE
        s['index'] += 1
        input_field.value = ""
        _next(page)

    def _next(page):
        s = page.spelling_state
        if s['index'] >= len(s['items']):
            _finish(page)
        else:
            item = s['items'][s['index']]
            trans_text.value = item['trans']
            status_text.value = f"第 {s['index'] + 1}/{len(s['items'])} 个"
            result_text.value = ""
            result_text.color = None
        page.update()

    def _finish(page):
        s = page.spelling_state
        trans_text.value = ""
        input_field.visible = False
        submit_btn.disabled = True
        skip_btn.disabled = True
        result_text.value = ""
        acc = round(s['correct'] / s['answered'] * 100, 1) if s['answered'] else 0
        status_text.value = f"本组拼写测试完成：正确 {s['correct']}/{s['answered']}（{acc}%）"
        page.update()

    _next(page)

    return ft.Column(
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Row([back_btn], alignment=ft.MainAxisAlignment.START),
            ft.Text("拼写测试", size=24, weight=ft.FontWeight.BOLD),
            trans_text,
            input_field,
            ft.Row([submit_btn, skip_btn], alignment=ft.MainAxisAlignment.CENTER),
            result_text,
            status_text,
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=16,
    )
