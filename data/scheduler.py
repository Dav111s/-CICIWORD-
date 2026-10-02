# data/scheduler.py
"""艾宾浩斯复习调度（经典间隔阶梯）。"""

# 经典艾宾浩斯间隔阶梯（天）：按连续答对次数递增
EBBINGHAUS_LADDER = [1, 2, 4, 7, 15, 30]


def get_ebbinghaus_interval(streak: int) -> int:
    """
    根据连续答对次数返回下次复习间隔（天）。
    streak=1 -> 1天, 2 -> 2天, 3 -> 4天, 4 -> 7天, 5 -> 15天, >=6 -> 30天。
    """
    streak = max(0, int(streak))
    idx = min(streak - 1, len(EBBINGHAUS_LADDER) - 1)
    idx = max(0, idx)
    return EBBINGHAUS_LADDER[idx]
