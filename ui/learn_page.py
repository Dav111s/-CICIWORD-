# ui/learn_page.py
"""学习模式：三关闯关流程。

- 第1关（选择题）：只渲染单词卡 + 4 个简约选项按钮，不创建任何底部按钮容器。
- 第2/3关：认识/不认识按钮，用 if 条件添加到根 Column（不用 visible 隐藏）。
- 答后：提示、释义、科目标签直接渲染到主单词卡片内部，不再单独弹灰色卡片。
"""
import random
import time

import flet as ft

from config import get_current_book, get_study_group_size, add_study_duration, is_spelling_test_enabled
from data import db, universe
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR


def build_learn_page(page: ft.Page) -> ft.Control:
    page.learn_state = {
        'mode': 'learn',
        'group_ids': [],
        'pending': [],
        'completed': [],
        'current_id': None,
        'start_time': time.time(),
        'mcq_correct_index': 0,
        'tentative_correct': True,
    }

    # ---- 顶栏 ----
    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回首页", on_click=lambda e: page.go("/"))
    favorite_btn = ft.IconButton(icon=ft.Icons.STAR_BORDER, tooltip="收藏", on_click=lambda e: _toggle_favorite(page))
    known_btn = ft.TextButton("标记熟词", on_click=lambda e: _mark_known(page))
    progress_text = ft.Text("", size=13, color=ft.Colors.GREY)
    header_row = ft.Row(
        [back_btn, ft.Container(progress_text, expand=True, alignment=ft.alignment.center), favorite_btn, known_btn],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    # ---- 主单词卡片（唯一卡片容器）：英文 + 答后追加 提示/释义/标签 ----
    word_text = ft.Text("", size=26, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    word_card_body = ft.Column(
        [word_text],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=6,
    )
    word_card = glass(word_card_body, height=200, radius=20, padding=20)

    # ---- 第1关：4 个简约选项（ResponsiveRow：窄窗口占满整行，宽窗口自动收窄，不横向溢出） ----
    option_col = ft.ResponsiveRow(spacing=10, run_spacing=10, alignment=ft.MainAxisAlignment.CENTER)
    option_area = ft.Container(content=option_col, visible=False)

    # ---- 第2关：例句提示 ----
    example_text = ft.Text("", size=15, italic=True, text_align=ft.TextAlign.CENTER)
    example_card = glass(
        ft.Column([example_text], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=18, radius=16,
    )
    example_card.visible = False

    # ---- 第3关：无提示 ----
    level3_hint = ft.Text("请在无提示的情况下判断", size=13, color=ft.Colors.ORANGE, visible=False)

    # ---- 认识/不认识（第2/3关），作为底部栏条件添加 ----
    known_action = glass_button("认识", lambda e: _answer(page, True), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)
    unknown_action = glass_button("不认识", lambda e: _answer(page, False), tint=ft.Colors.RED_400, opacity=0.32, text_color=ft.Colors.RED_900)
    action_row = ft.Row(
        [known_action, unknown_action],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=16,
        run_spacing=12,
        wrap=True,
    )
    action_bar = ft.Container(
        content=action_row,
        padding=ft.padding.symmetric(vertical=12),
        alignment=ft.alignment.center,
    )

    # ---- 答后底部按钮 ----
    next_btn = glass_button("下一个", lambda e: _commit(page, None), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)
    flip_btn = glass_button("记错了", lambda e: _commit(page, True), tint=ft.Colors.ORANGE, opacity=0.32, text_color=ft.Colors.ORANGE_900)
    bottom_bar = ft.Container(
        content=ft.Row(
            [next_btn, flip_btn],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
            run_spacing=12,
            wrap=True,
        ),
        padding=ft.padding.symmetric(vertical=12),
        alignment=ft.alignment.center,
    )

    # ---- 滚动区（不含底部按钮） ----
    layout = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[header_row, word_card, option_area, example_card, level3_hint],
        spacing=16,
    )
    scroll_container = ft.Container(content=layout, expand=True, padding=ft.padding.symmetric(horizontal=16, vertical=12))

    # 根 Column：只含滚动区，底部按钮按需 if 添加/移除
    # horizontal_alignment=STRETCH：底部栏撑满窗口宽度，按钮组才能整体水平居中（否则底部栏只有内容宽，靠左）
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

        只修改 children，不调用未挂载控件的 .update()（由调用方的 page.update() 统一刷新），
        避免路由初始加载时 word_card_body 尚未挂载就 update 触发 AssertionError。
        """
        word_card_body.controls = [word_text] + controls

    def _build_mcq(word):
        state = page.learn_state
        correct = word['trans']
        distractors = [d for d in db.get_distractors(word['id'], get_current_book(), 3) if d != correct]
        options = [correct] + distractors
        while len(options) < 4:
            options.append("（暂无干扰项）")
        options = options[:4]
        random.shuffle(options)
        state['mcq_correct_index'] = options.index(correct)
        option_col.controls = [
            # 简约紧凑选项：减小 padding/高度、适度圆角，保留点击高亮，文字深色可读
            # col 自适应：窄窗口整行铺满，宽窗口按比例收窄，避免固定 300 宽在窄屏溢出
            ft.Container(
                content=ft.Text(opt, size=14, color="#222222", text_align=ft.TextAlign.CENTER),
                col={"xs": 12, "sm": 8, "md": 6, "lg": 5},
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
                border_radius=10,
                bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                border=ft.border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
                ink=True,
                alignment=ft.alignment.center,
                on_click=lambda e, i=idx: _answer(page, i == state['mcq_correct_index']),
            )
            for idx, opt in enumerate(options)
        ]

    def _render_question():
        state = page.learn_state
        _set_card_detail([])  # 重置卡片为纯英文

        if state['current_id'] is None:
            progress_text.value = ""
            word_text.value = "暂无新词可学，去词库导入或切换词库吧"
            favorite_btn.visible = False
            known_btn.visible = False
            option_area.visible = False
            example_card.visible = False
            level3_hint.visible = False
            _set_bottom(False, False)  # 无任何底部按钮
            page.update()
            return

        word = db.get_word_by_id(state['current_id'])
        stage = int(word.get('stage') or 1)
        progress_text.value = f"本组进度 {len(state['completed'])}/{len(state['group_ids'])}"
        word_text.value = word['word']

        favorite_btn.visible = True
        known_btn.visible = True
        favorite_btn.icon = ft.Icons.STAR if word.get('favorite') else ft.Icons.STAR_BORDER

        option_area.visible = (stage == 1)
        example_card.visible = (stage == 2)
        level3_hint.visible = (stage == 3)

        if stage == 1:
            _build_mcq(word)
            _set_bottom(False, False)  # 选择题：不创建任何底部按钮
        elif stage == 2:
            example_text.value = f"例句：{word['example']}" if word.get('example') else ""
            _set_bottom(True, False)   # 认识/不认识
        else:
            _set_bottom(True, False)   # 认识/不认识
        page.update()

    def _answer(page, correct):
        state = page.learn_state
        if state['current_id'] is None or state.get('_answered'):
            return
        state['_answered'] = True
        state['tentative_correct'] = correct
        word = db.get_word_by_id(state['current_id'])

        option_area.visible = False
        example_card.visible = False
        level3_hint.visible = False

        tags = universe.get_stage_tags(word['word'])
        detail = [
            ft.Text("✓ 答对了" if correct else "✗ 答错了", size=17, weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREEN_900 if correct else ft.Colors.RED_900),
            ft.Text(f"释义：{word['trans']}", size=15),
        ]
        if tags:
            detail.append(ft.Text("  ".join(f"#{t}" for t in tags), size=13, color=SUB_TEXT_COLOR))
        _set_card_detail(detail)   # 合并进主卡片
        next_btn.visible = True
        flip_btn.visible = correct
        _set_bottom(False, True)   # 只显示 下一个/记错了
        page.update()

    def _commit(page, flip):
        state = page.learn_state
        wid = state['current_id']
        if wid is None:
            return
        is_correct = state['tentative_correct']
        if flip:
            is_correct = False
        word, interval, completed = db.submit_answer(wid, is_correct, 'learn')
        if completed:
            state['completed'].append({
                'id': wid, 'word': word['word'], 'trans': word['trans'], 'interval': interval,
            })
            if wid in state['pending']:
                state['pending'].remove(wid)
        state['_answered'] = False
        _next(page)

    def _next(page):
        state = page.learn_state
        if not state['pending']:
            _finish_group(page)
            return
        candidates = [w for w in state['pending'] if w != state['current_id']]
        if not candidates:
            candidates = list(state['pending'])
        state['current_id'] = random.choice(candidates)
        _render_question()

    def _finish_group(page):
        state = page.learn_state
        add_study_duration(int(time.time() - state['start_time']))
        words = [{'id': it['id'], 'word': it['word'], 'trans': it['trans']} for it in state['completed']]
        page.spelling_state = {'words': words, 'return_route': '/summary'}
        if is_spelling_test_enabled() and words:
            page.go("/spelling")
        else:
            page.go("/summary")

    def _toggle_favorite(page):
        wid = page.learn_state['current_id']
        if wid is None:
            return
        word = db.get_word_by_id(wid)
        new_val = 0 if word.get('favorite') else 1
        db.set_word_favorite(wid, new_val)
        favorite_btn.icon = ft.Icons.STAR if new_val else ft.Icons.STAR_BORDER
        page.update()

    def _mark_known(page):
        state = page.learn_state
        wid = state['current_id']
        if wid is None:
            return
        word = db.mark_word_known(wid)
        state['completed'].append({
            'id': wid, 'word': word['word'], 'trans': word['trans'], 'interval': 30,
        })
        if wid in state['pending']:
            state['pending'].remove(wid)
        state['_answered'] = False
        _next(page)

    page.learn_state['render'] = _render_question

    return page_shell(page, root_col)


def load_learn_data(page: ft.Page):
    """供 main.py 调用：加载一组新词并渲染。"""
    state = page.learn_state
    book = get_current_book()
    group = db.get_learn_queue(book, get_study_group_size())
    state['group_ids'] = [w['id'] for w in group]
    state['pending'] = [w['id'] for w in group]
    state['completed'] = []
    state['current_id'] = random.choice(state['pending']) if state['pending'] else None
    state['_answered'] = False
    state['start_time'] = time.time()
    state['render']()
