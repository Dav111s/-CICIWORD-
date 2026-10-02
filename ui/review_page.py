# ui/review_page.py
"""复习模式：三档反馈（记住/模糊/忘记）+ 词义详情两阶段交互。

- 答后：提示文字、释义、科目标签直接渲染到主单词卡片内部，不再单独弹出灰色卡片。
- 底部按钮用 if 条件添加/移除到根 Column，不用 visible 隐藏（避免残留占位容器）。
"""
import flet as ft

from config import get_current_book, is_spelling_test_enabled
from data import db, universe
from srs import ReviewFeedback
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR


def build_review_page(page: ft.Page) -> ft.Control:
    page.review_state = {
        'queue': [], 'index': 0, 'tentative_feedback': ReviewFeedback.REMEMBER,
        '_answered': False, 'reviewed': {},
    }

    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回首页", on_click=lambda e: page.go("/"))
    title_text = ft.Text("复习模式", size=20, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
    remain_text = ft.Text("", size=13, color=ft.Colors.GREY)

    # 主单词卡片（唯一卡片容器）：英文 + 答后追加 提示/释义/标签
    word_text = ft.Text("", size=26, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    word_card_body = ft.Column(
        [word_text],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=6,
    )
    word_card = glass(word_card_body, height=200, radius=20, padding=20)

    remember_btn = glass_button("记住🟢", lambda e: _answer(page, ReviewFeedback.REMEMBER), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)
    hazy_btn = glass_button("模糊🟡", lambda e: _answer(page, ReviewFeedback.HAZY), tint=ft.Colors.AMBER_400, opacity=0.32, text_color=ft.Colors.AMBER_900)
    forget_btn = glass_button("忘记🔴", lambda e: _answer(page, ReviewFeedback.FORGET), tint=ft.Colors.RED_400, opacity=0.32, text_color=ft.Colors.RED_900)
    # 三个按钮：Row 内水平居中 + 窄窗口自动换行（间距不变、按钮尺寸/配色不变）
    action_row = ft.Row(
        [remember_btn, hazy_btn, forget_btn],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=12,
        run_spacing=12,
        wrap=True,
    )
    # alignment=center：容器被拉伸到整行宽后，按钮组在容器内部整体居中
    action_bar = ft.Container(
        content=action_row,
        padding=ft.padding.symmetric(vertical=12),
        alignment=ft.alignment.center,
    )

    status_text = ft.Text("请在无提示的情况下选择记住/模糊/忘记", size=14)

    next_btn = glass_button("下一个", lambda e: _commit(page), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)
    bottom_bar = ft.Container(
        content=ft.Row([next_btn], alignment=ft.MainAxisAlignment.CENTER),
        padding=ft.padding.symmetric(vertical=12),
        alignment=ft.alignment.center,
    )

    header_row = ft.Row([back_btn, title_text], alignment=ft.MainAxisAlignment.START)

    # 滚动区（不含底部按钮）
    layout = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[header_row, remain_text, word_card, status_text],
        spacing=16,
    )
    scroll_container = ft.Container(content=layout, expand=True, padding=ft.padding.symmetric(horizontal=16, vertical=12))

    # 根 Column：只含滚动区，底部按钮按需 if 添加/移除
    # horizontal_alignment=STRETCH：让底部栏撑满窗口宽度，按钮组才能真正水平居中（否则底部栏只有内容宽，靠左）
    root_col = ft.Column(
        [scroll_container],
        expand=True,
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    def _set_bottom(show_action=False, show_next=False):
        """底部按钮条件渲染：重建 root_col.controls，不添加则不占位。

        只改 children，不单独 update（由调用方 page.update() 统一刷新）。
        """
        root_col.controls = [scroll_container]
        if show_action:
            root_col.controls.append(action_bar)
        if show_next:
            root_col.controls.append(bottom_bar)

    def _set_card_detail(controls):
        """把答后内容合并进主单词卡片（不再新建灰色弹窗）。

        只修改 children，不调用未挂载控件的 .update()（由调用方 page.update() 统一刷新），
        避免路由初始加载时 word_card_body 尚未挂载就 update 触发 AssertionError。
        """
        word_card_body.controls = [word_text] + controls

    def _render():
        state = page.review_state
        state['_answered'] = False
        _set_card_detail([])  # 重置卡片为纯英文
        if not state['queue']:
            _set_bottom(False, False)
            remain_text.value = ""
            status_text.value = "🎉 今日复习已完成！"
            word_card.visible = False  # 无词时隐藏卡片（内容卡，非底部占位）
            page.update()
            return
        word = state['queue'][state['index']]
        word_card.visible = True
        word_text.value = word['word']
        remain_text.value = f"剩余 {len(state['queue'])} 个单词"
        status_text.value = "请在无提示的情况下选择记住/模糊/忘记"
        _set_bottom(True, False)  # 显示 记住/模糊/忘记
        page.update()

    def _answer(page, feedback):
        state = page.review_state
        if not state['queue'] or state['_answered']:
            return
        state['_answered'] = True
        state['tentative_feedback'] = feedback
        word = state['queue'][state['index']]

        if feedback == ReviewFeedback.REMEMBER:
            head, hcolor = "✓ 记住", ft.Colors.GREEN_900
        elif feedback == ReviewFeedback.HAZY:
            head, hcolor = "◐ 模糊", ft.Colors.AMBER_900
        else:
            head, hcolor = "✗ 忘记", ft.Colors.RED_900

        tags = universe.get_stage_tags(word['word'])
        detail = [
            ft.Text(head, size=17, weight=ft.FontWeight.BOLD, color=hcolor),
            ft.Text(f"释义：{word['trans']}", size=15),
        ]
        if tags:
            detail.append(ft.Text("  ".join(f"#{t}" for t in tags), size=13, color=SUB_TEXT_COLOR))
        _set_card_detail(detail)   # 合并进主卡片
        _set_bottom(False, True)   # 只显示 下一个
        page.update()

    def _commit(page):
        state = page.review_state
        if not state['queue']:
            return
        word = state['queue'][state['index']]
        wid = word['id']
        fb = state['tentative_feedback']
        db.submit_review_three_tier(wid, fb)
        state['reviewed'][wid] = {'id': wid, 'word': word['word'], 'trans': word['trans']}

        if fb == ReviewFeedback.FORGET:
            state['queue'].append(state['queue'].pop(state['index']))
        else:
            state['queue'].pop(state['index'])
        if state['index'] >= len(state['queue']):
            state['index'] = 0
        if not state['queue']:
            _finish_review(page)
        else:
            _render()

    def _finish_review(page):
        state = page.review_state
        words = list(state['reviewed'].values())
        page.spelling_state = {'words': words, 'return_route': '/'}
        try:
            from ai.memory_model import should_train, train_async
            if should_train():
                train_async()
        except Exception:
            pass
        if is_spelling_test_enabled() and words:
            page.go("/spelling")
        else:
            _render()

    page.review_state['render'] = _render

    return page_shell(page, root_col)


def load_review_data(page: ft.Page):
    """供 main.py 调用：加载复习队列并渲染。"""
    state = page.review_state
    book = get_current_book()
    state['queue'] = db.get_review_queue(book)
    state['index'] = 0
    state['reviewed'] = {}
    state['render']()
