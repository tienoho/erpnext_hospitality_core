"""Quy tắc giá thuần túy, dùng chung cho báo giá và ghi tiền phòng."""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def money(value, precision=2):
    number = Decimal(str(value or 0))
    if not number.is_finite():
        raise ValueError('Số tiền phải là giá trị hữu hạn.')
    return float(number.quantize(
        Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP))


def validate_rules(seasons, tiers):
    seen = []
    for season in seasons:
        start, end = as_date(season['valid_from']), as_date(season['valid_to'])
        if start > end:
            raise ValueError('Ngày bắt đầu mùa vụ không được sau ngày kết thúc.')
        if float(season.get('weekday_rate') or 0) < 0 or float(season.get('weekend_rate') or 0) < 0:
            raise ValueError('Giá mùa vụ không được âm.')
        if any(start <= b and end >= a for a, b in seen):
            raise ValueError('Các mùa vụ trong cùng bảng giá không được trùng ngày.')
        seen.append((start, end))
    thresholds = set()
    for tier in tiers:
        nights = int(tier.get('min_nights') or 0)
        if nights < 1 or nights != float(tier.get('min_nights') or 0):
            raise ValueError('Số đêm tối thiểu phải là số nguyên từ 1 trở lên.')
        if nights in thresholds:
            raise ValueError('Không được có hai bậc LOS cùng số đêm tối thiểu.')
        if not 0 <= float(tier.get('discount_percent') or 0) <= 100:
            raise ValueError('Giảm giá LOS phải trong khoảng 0–100%.')
        thresholds.add(nights)


def discount_breakdown(base_rate, tiers, nights, eligible=True,
                       discount_type=None, discount_value=0, complimentary=False, precision=2, vip_percent=0):
    value = float(discount_value or 0)
    if not isfinite(value) or value < 0 or (discount_type == 'Percentage' and value > 100):
        raise ValueError('Giảm giá phải không âm; tỷ lệ giảm không được vượt 100%.')
    base_rate = money(base_rate, precision)
    if base_rate < 0:
        raise ValueError('Giá phòng không được âm.')
    tier = max((t for t in tiers if int(t['min_nights']) <= nights),
               key=lambda t: int(t['min_nights']), default=None) if eligible else None
    pct = float(tier['discount_percent']) if tier else 0
    los_amount = money(base_rate * pct / 100, precision)
    after_los = money(base_rate - los_amount, precision)
    if not 0 <= float(vip_percent or 0) <= 100:
        raise ValueError('Giảm giá VIP phải trong khoảng 0–100%.')
    vip_amount = money(after_los * float(vip_percent or 0) / 100, precision)
    after_vip = money(after_los - vip_amount, precision)
    manual = after_vip if complimentary else (
        after_vip * value / 100 if discount_type == 'Percentage' else
        value if discount_type == 'Amount' else 0)
    manual = money(min(after_vip, manual), precision)
    return dict(base_rate=base_rate, los_percent=pct, los_min_nights=int(tier['min_nights']) if tier else 0,
                los_discount=los_amount, rate_after_los=after_los, manual_discount=manual,
                vip_percent=float(vip_percent or 0), vip_discount=vip_amount, rate_after_vip=after_vip,
                discount_amount=money(los_amount + vip_amount + manual, precision),
                final_rate=money(after_vip - manual, precision))


def quote_day(snapshot, target_date, arrival_date=None, departure_date=None,
              discount_type=None, discount_value=0, complimentary=False):
    target = as_date(target_date)
    seasons, tiers = snapshot.get('seasons', []), snapshot.get('los_discounts', [])
    validate_rules(seasons, tiers)
    season = next((s for s in seasons if as_date(s['valid_from']) <= target <= as_date(s['valid_to'])), None)
    weekend = target.weekday() in (4, 5)
    base = snapshot.get('default_rate', 0)
    if season:
        base = (season.get('weekend_rate') if weekend and float(season.get('weekend_rate') or 0) > 0
                else season.get('weekday_rate'))
    nights = 0
    if arrival_date and departure_date:
        nights = (as_date(departure_date) - as_date(arrival_date)).days
        if nights < 1:
            raise ValueError('Ngày trả phòng phải sau ngày nhận phòng.')
    # Kế hoạch v2 đã chốt: giá mặc định không áp LOS; VIP tính sau LOS.
    result = discount_breakdown(base, tiers, nights, bool(season), discount_type,
                                discount_value, complimentary, snapshot.get('precision', 2), snapshot.get('vip_percent', 0))
    result.update(date=str(target), season_name=season.get('season_name') if season else None,
                  source='season' if season else 'default', weekend=weekend, nights=nights,
                  currency=snapshot.get('currency'), property=snapshot.get('property'))
    return result


def quote_stay(snapshot, arrival_date, departure_date, **discounts):
    start, end = as_date(arrival_date), as_date(departure_date)
    if not 0 < (end - start).days <= 3660:
        raise ValueError('Kỳ lưu trú phải từ 1 đến 3660 đêm.')
    rows = [quote_day(snapshot, start + timedelta(days=i), start, end, **discounts)
            for i in range((end - start).days)]
    precision = snapshot.get('precision', 2)
    return dict(nightly_rates=rows, total=money(sum(r['final_rate'] for r in rows), precision),
                total_discount=money(sum(r['discount_amount'] for r in rows), precision), nights=len(rows))
