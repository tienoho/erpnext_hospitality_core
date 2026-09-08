"""Phép tính điểm thuần túy, độc lập database."""


def redemption_capacity(balance, held, own_hold):
    return balance - held + own_hold


def qualification_delta(earned, target, redeemed=0, expired=0, lot_expired=False):
    """Giữ lịch hết hạn gốc, không trừ hai lần phần điểm đã hết hạn."""
    point_delta = target - earned
    desired_expired = max(0, target - redeemed) if lot_expired else expired
    return point_delta, expired - desired_expired

