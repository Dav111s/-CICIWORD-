# ui/stats_page.py
"""数据统计主页（仪表盘）：今日总结 / 学习总览 / 正确率趋势 / 遗忘曲线。

本次只改布局与自适应，**没有改统计口径、遗忘曲线数据计算与遗忘预测算法**：
- 卡片统一用 ResponsiveRow：窄窗口 1~2 列、宽窗口多列，窗口缩放时自动重排、不横向截断。
- 图表宽度交给 Row 里 expand 的子项撑满、高度固定；expand 不能直接挂在可滚动 Column
  的子项上（高度约束无界会把图表压扁，表现为坐标轴 / 曲线边界被裁切）。
- refresh_stats_page()：进入 /stats 路由时重新读库（main.py 调用），保证
  「学完一轮 → 返回统计主页」立即显示最新今日统计，无需重启应用。
"""
import flet as ft

from config import get_current_book
from data import statistics as st
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR

# 图表固定高度（宽度自适应，由外层 Row 的 Expanded 撑满）
CHART_HEIGHT = 260
# 正确率趋势默认周期
DEFAULT_TREND_DAYS = 7


def build_stats_page(page: ft.Page) -> ft.Control:
    book = get_current_book()

    back_btn = glass_button("返回首页", lambda _: page.go("/"))

    # key -> 数值 Text 控件，供 _refresh() 就地更新
    values = {}

    def _metric(title, key, subtitle="", col=None, value_size=26):
        """毛玻璃统计卡：标题 + 数值 + 说明，宽度由 ResponsiveRow 的 col 自适应。"""
        value_text = ft.Text("", size=value_size, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
        values[key] = value_text
        return glass(
            ft.Column(
                [
                    ft.Text(title, size=13, color=SUB_TEXT_COLOR),
                    value_text,
                    ft.Text(subtitle, size=11, color=SUB_TEXT_COLOR) if subtitle else ft.Text(" ", size=11),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            padding=14,
            radius=16,
            col=col,
        )

    def _section_title(title, subtitle=""):
        children = [ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)]
        if subtitle:
            children.append(ft.Text(subtitle, size=12, color=SUB_TEXT_COLOR))
        return ft.Column(children, spacing=2, horizontal_alignment=ft.CrossAxisAlignment.START)

    # ---- 今日总结（窄屏 1 列 / ≥sm 三列并排） ----
    today_cards = ft.ResponsiveRow(
        controls=[
            _metric("今日学习", "today_learn", "今日新学记录", col={"xs": 12, "sm": 4}, value_size=30),
            _metric("今日复习", "today_review", "今日复习次数", col={"xs": 12, "sm": 4}, value_size=30),
            _metric("待学新词", "new_words", "尚未开始学习", col={"xs": 12, "sm": 4}, value_size=30),
        ],
        spacing=12,
        run_spacing=12,
        alignment=ft.MainAxisAlignment.CENTER,
    )
    today_hint = ft.Text("", size=13, color=SUB_TEXT_COLOR)

    # ---- 学习总览（窄屏 2 列 / ≥sm 四列并排） ----
    overview_cards = ft.ResponsiveRow(
        controls=[
            _metric("总单词数", "total", col={"xs": 6, "sm": 3}),
            _metric("已学习", "learned", col={"xs": 6, "sm": 3}),
            _metric("已掌握", "mastered", "连续答对≥3次", col={"xs": 6, "sm": 3}),
            _metric("拼写正确率", "spelling", col={"xs": 6, "sm": 3}),
        ],
        spacing=12,
        run_spacing=12,
        alignment=ft.MainAxisAlignment.CENTER,
    )

    # ---- 正确率趋势 ----
    trend_label = ft.Text(f"近{DEFAULT_TREND_DAYS}天正确率趋势", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
    trend_box = ft.Container(content=_build_accuracy_chart(book, DEFAULT_TREND_DAYS))
    state = {'days': DEFAULT_TREND_DAYS}

    def _on_period_change(e):
        days = int(e.control.value or DEFAULT_TREND_DAYS)
        state['days'] = days
        trend_label.value = f"近{days}天正确率趋势"
        trend_box.content = _build_accuracy_chart(book, days)
        page.update()

    period_dropdown = ft.Dropdown(
        label="趋势周期",
        width=124,
        options=[
            ft.dropdown.Option("7", "近7天"),
            ft.dropdown.Option("30", "近30天"),
        ],
        value=str(DEFAULT_TREND_DAYS),
        on_change=_on_period_change,
    )

    trend_header = ft.Row(
        [trend_label, period_dropdown],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        wrap=True,
        spacing=8,
        run_spacing=8,
    )

    # ---- 遗忘曲线 ----
    forgetting_box = ft.Container(content=_build_forgetting_chart(book))

    def _read_values():
        return {
            'total': st.get_total_words_count(book),
            'learned': st.get_learned_words_count(book),
            'mastered': st.get_mastered_words_count(book),
            'today_learn': st.get_today_study_count(book),
            'today_review': st.get_today_reviewed_count(book),
            'new_words': st.get_new_words_count(book),
            'spelling': _spelling_text(book),
        }

    def _refresh():
        """重读数据库并就地刷新数值与图表。

        只改控件属性 / 内容，不调用 page.update()（由调用方统一刷新），
        避免未挂载控件的 update 触发 AssertionError。
        """
        vals = _read_values()
        for key, ctrl in values.items():
            ctrl.value = str(vals.get(key, ''))
        today_hint.value = (
            f"今日已学习 {vals['today_learn']} 条 · 今日已复习 {vals['today_review']} 条 · "
            f"待学新词 {vals['new_words']} 个"
        )
        trend_box.content = _build_accuracy_chart(book, state['days'])
        forgetting_box.content = _build_forgetting_chart(book)

    # 暴露给 main.py：路由进入 /stats 时强制重读统计（无需重启即可看到最新数据）
    page.stats_refresh = _refresh
    _refresh()

    return page_shell(
        page,
        ft.Container(
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row([back_btn], alignment=ft.MainAxisAlignment.START),
                    ft.Text("数据统计", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                    _section_title("今日总结", "学习 / 复习 / 待学新词"),
                    today_cards,
                    today_hint,
                    _section_title("学习总览"),
                    overview_cards,
                    trend_header,
                    trend_box,
                    _section_title("遗忘曲线", "间隔天数 → 记忆保持率"),
                    forgetting_box,
                ],
                alignment=ft.MainAxisAlignment.START,
                spacing=16,
            ),
            expand=True,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    )


def refresh_stats_page(page: ft.Page):
    """供 main.py 在进入 /stats 路由时调用：重读数据库，立即刷新今日统计。

    页面未构建过（无 stats_refresh）时静默跳过，由 build_stats_page 自行渲染最新数据。
    """
    refresh = getattr(page, 'stats_refresh', None)
    if callable(refresh):
        refresh()


def _spelling_text(book) -> str:
    sp_total, sp_correct = st.get_spelling_stats(book)
    return f"{round(sp_correct / sp_total * 100, 1)}%" if sp_total else "暂无"


def _chart_block(chart: ft.Control, caption: str = "") -> ft.Control:
    """图表外框：宽度由 Row 中 expand 的子项撑满，高度由图表自身固定，避免被裁切。"""
    row = ft.Row(
        [chart],
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    if not caption:
        return row
    return ft.Column(
        [
            row,
            ft.Text(caption, size=12, color=SUB_TEXT_COLOR, text_align=ft.TextAlign.CENTER),
        ],
        spacing=6,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def _build_accuracy_chart(book, days=7) -> ft.Control:
    """近 N 天正确率趋势折线图（数据来源不变：statistics.get_accuracy_trend）。"""
    data = st.get_accuracy_trend(days, book)
    points = [ft.LineChartDataPoint(i, acc) for i, (_, acc) in enumerate(data) if acc is not None]

    series = []
    if points:
        series.append(
            ft.LineChartData(
                data_points=points,
                stroke_width=3,
                color=ft.Colors.PURPLE,
                curved=True,
                stroke_cap_round=True,
            )
        )

    # 底部日期标签：天数多时隔几天显示一个，且不贴在首尾两端，避免标签被裁切 / 互相挤压
    if days <= 7:
        label_indexes = list(range(len(data)))
    else:
        step = max(1, days // 6)
        label_indexes = [i for i in range(len(data)) if i % step == 0 and 1 <= i <= len(data) - 2]

    return _chart_block(
        ft.LineChart(
            data_series=series,
            min_y=0,
            max_y=100,
            # 左右各留半格空白：避免端点曲线与首尾标签被图表边界切掉
            min_x=-0.5,
            max_x=max(days - 1, 1) + 0.5,
            height=CHART_HEIGHT,
            expand=True,
            left_axis=ft.ChartAxis(labels_size=38, title=ft.Text("正确率%", size=11), title_size=24),
            bottom_axis=ft.ChartAxis(
                labels_size=40,
                labels=[
                    ft.ChartAxisLabel(value=i, label=ft.Text(data[i][0][5:], size=11))
                    for i in label_indexes
                ],
            ),
            horizontal_grid_lines=ft.ChartGridLines(interval=25, color=ft.Colors.GREY_300, width=1),
            tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.PURPLE_100),
        ),
        caption="" if points else "暂无复习记录：完成一轮复习后自动生成正确率趋势",
    )


def _build_forgetting_chart(book) -> ft.Control:
    """遗忘曲线（绘图与数据计算逻辑不变）：间隔天数 → 记忆保持率。"""
    data = st.get_forgetting_curve(book)
    points = [ft.LineChartDataPoint(g, keep) for g, keep in data]

    series = []
    if points:
        series.append(
            ft.LineChartData(
                data_points=points,
                stroke_width=3,
                color=ft.Colors.PINK,
                curved=True,
                stroke_cap_round=True,
            )
        )

    max_gap = max((g for g, _ in data), default=1)
    pad = max(0.5, max_gap * 0.06)  # 右侧留白：曲线末端点不被边界裁切
    labels = [ft.ChartAxisLabel(value=g, label=ft.Text(str(g), size=11)) for g, _ in data]
    if len(labels) > 8:  # 间隔点过多时隔一个显示，避免标签重叠
        labels = [lb for i, lb in enumerate(labels) if i % 2 == 0 or i == len(labels) - 1]

    return _chart_block(
        ft.LineChart(
            data_series=series,
            min_y=0,
            max_y=100,
            min_x=-pad,
            max_x=max_gap + pad,
            height=CHART_HEIGHT,
            expand=True,
            left_axis=ft.ChartAxis(labels_size=38, title=ft.Text("保持率%", size=11), title_size=24),
            bottom_axis=ft.ChartAxis(
                labels_size=40,
                title=ft.Text("间隔天数", size=11),
                title_size=24,
                labels=labels,
            ),
            horizontal_grid_lines=ft.ChartGridLines(interval=25, color=ft.Colors.GREY_300, width=1),
            tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.PINK_100),
        ),
        caption="" if points else "暂无复习记录：完成一轮复习后自动生成遗忘曲线",
    )
