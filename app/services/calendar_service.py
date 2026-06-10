import json
import os
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.calendar import CalendarDay, YearCalendar

# ── Загрузка справочника праздников и переносов ──────────────────────────

_TRANSFERS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "calendar_holidays.json")

_transfers_cache: Optional[dict] = None


def _load_transfers() -> dict:
    """Загрузить JSON с праздниками и переносами (с кэшем)."""
    global _transfers_cache
    if _transfers_cache is not None:
        return _transfers_cache
    try:
        with open(_TRANSFERS_PATH, "r", encoding="utf-8") as f:
            _transfers_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[CALENDAR] Ошибка загрузки transfers.json: {e}")
        _transfers_cache = {"holidays": {}, "transfers": {}}
    return _transfers_cache


# ── Генерация календаря с праздниками и переносами ──────────────────────


def _generate_calendar(year: int) -> list[dict]:
    """
    Сгенерировать календарь на указанный год с учётом:
    - фиксированных государственных праздников
    - переносов выходных (из transfers.json)
    Возвращает список {day, is_holiday, is_short_day, holiday_name}.
    """
    data = _load_transfers()
    fixed_holidays = data.get("holidays", {})
    transfers = data.get("transfers", {}).get(str(year), {})

    results = []
    current = date(year, 1, 1)
    end = date(year, 12, 31)

    # Строим множество дней, которые стали выходными благодаря переносам
    transfer_holidays = set()
    for target, source in transfers.items():
        try:
            m, d = map(int, target.split("-"))
            transfer_holidays.add(date(year, m, d))
        except (ValueError, IndexError):
            pass

    # Авто-перенос: если госпраздник выпал на СБ/ВС → перенос на ближайший рабочий день
    for mmdd, name in fixed_holidays.items():
        try:
            m, d = map(int, mmdd.split("-"))
            holiday_date = date(year, m, d)
            if holiday_date.weekday() >= 5:
                # Ищем ближайший рабочий день (понедельник)
                next_workday = holiday_date + timedelta(days=1)
                while next_workday.weekday() >= 5 or next_workday.strftime("%m-%d") in fixed_holidays:
                    next_workday += timedelta(days=1)
                transfer_holidays.add(next_workday)
        except (ValueError, IndexError):
            pass

    while current <= end:
        month_day_key = current.strftime("%m-%d")

        # Определяем статус дня
        is_fixed_holiday = month_day_key in fixed_holidays
        is_transfer_holiday = current in transfer_holidays
        is_weekend = current.weekday() >= 5

        is_holiday = is_fixed_holiday or is_transfer_holiday or is_weekend
        is_short_day = False  # Сокращённые дни можно добавить позже в JSON

        holiday_name = fixed_holidays.get(month_day_key, "")

        results.append({
            "day": current,
            "is_holiday": is_holiday,
            "is_short_day": is_short_day,
            "holiday_name": holiday_name,
        })
        current += timedelta(days=1)

    return results


# ── Сохранение в БД ────────────────────────────────────────────────────────


def save_calendar_to_db(db: Session, year: int, days_data: list[dict]) -> bool:
    """Сохранить данные календаря в БД. Если за этот год уже есть — перезаписать."""
    old = db.query(YearCalendar).filter(YearCalendar.year == year).first()
    if old:
        db.delete(old)
        db.flush()

    cal = YearCalendar(year=year)
    db.add(cal)
    db.flush()

    for d in days_data:
        cd = CalendarDay(
            calendar_id=cal.id,
            day=d["day"],
            is_holiday=d["is_holiday"],
            is_short_day=d["is_short_day"],
        )
        db.add(cd)

    db.commit()
    return True


# ── Публичный API ──────────────────────────────────────────────────────────


def update_calendar_sync(db: Session, year: int) -> tuple[bool, str]:
    """
    Синхронное обновление календаря: генерация из локального справочника → сохранение в БД.
    """
    days_data = _generate_calendar(year)

    if not days_data:
        return False, f"Не удалось сформировать календарь за {year} год"

    save_calendar_to_db(db, year, days_data)

    holidays_count = sum(1 for d in days_data if d["is_holiday"])
    return True, f"Календарь за {year} год обновлён ({len(days_data)} дней, {holidays_count} выходных/праздников)"


def get_calendar_days(db: Session, year: int) -> list[dict]:
    """Получить все дни календаря за год (с названиями праздников)."""
    cal = db.query(YearCalendar).filter(YearCalendar.year == year).first()
    if not cal:
        return []

    data = _load_transfers()
    fixed_holidays = data.get("holidays", {})

    return [
        {
            "day": str(d.day),
            "is_holiday": d.is_holiday,
            "is_short_day": d.is_short_day,
            "holiday_name": fixed_holidays.get(d.day.strftime("%m-%d"), ""),
        }
        for d in sorted(cal.days, key=lambda x: x.day)
    ]


def get_month_calendar(db: Session, year: int, month: int) -> dict:
    """Получить календарь на конкретный месяц."""
    all_days = get_calendar_days(db, year)
    month_prefix = f"{year}-{month:02d}"
    month_days = [d for d in all_days if d["day"].startswith(month_prefix)]

    work_days = sum(1 for d in month_days if not d["is_holiday"])
    holidays = sum(1 for d in month_days if d["is_holiday"])
    short_days = sum(1 for d in month_days if d["is_short_day"])

    return {
        "year": year,
        "month": month,
        "total_days": len(month_days),
        "work_days": work_days,
        "holidays": holidays,
        "short_days": short_days,
        "days": month_days,
    }


def _save_transfers(data: dict) -> bool:
    """Сохранить обновлённый JSON с праздниками и переносами."""
    try:
        with open(_TRANSFERS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        global _transfers_cache
        _transfers_cache = data
        return True
    except Exception as e:
        print(f"[CALENDAR] Ошибка сохранения transfers.json: {e}")
        return False


def add_transfer(year: int, target: str, source: str) -> bool:
    """
    Добавить перенос выходного дня.
    target — день, который стал выходным (mm-dd)
    source — день, с которого перенос (mm-dd)
    """
    data = _load_transfers()
    year_str = str(year)
    if year_str not in data["transfers"]:
        data["transfers"][year_str] = {}
    data["transfers"][year_str][target] = source
    return _save_transfers(data)


def delete_transfer(year: int, target: str) -> bool:
    """Удалить перенос выходного дня."""
    data = _load_transfers()
    year_str = str(year)
    if year_str in data["transfers"] and target in data["transfers"][year_str]:
        del data["transfers"][year_str][target]
        if not data["transfers"][year_str]:
            del data["transfers"][year_str]
        return _save_transfers(data)
    return False


def get_transfers_for_year(year: int) -> list[dict]:
    """Получить список переносов для отображения в админке."""
    data = _load_transfers()
    year_str = str(year)
    transfers = data.get("transfers", {}).get(year_str, {})
    return [
        {"target": target, "source": source}
        for target, source in transfers.items()
    ]


def is_holiday(db: Session, check_date: date) -> bool:
    """Проверить, является ли день выходным/праздничным."""
    cal = db.query(YearCalendar).filter(YearCalendar.year == check_date.year).first()
    if not cal:
        return check_date.weekday() >= 5

    day_entry = (
        db.query(CalendarDay)
        .filter(
            CalendarDay.calendar_id == cal.id,
            CalendarDay.day == check_date,
        )
        .first()
    )

    if day_entry:
        return day_entry.is_holiday
    return check_date.weekday() >= 5