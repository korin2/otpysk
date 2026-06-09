import atexit
import threading
from datetime import date, timedelta
from typing import Optional

import httpx
from lxml import etree
from sqlalchemy.orm import Session

from app.models.calendar import CalendarDay, YearCalendar

# XML-источник производственного календаря РФ
CALENDAR_XML_URL = "https://production-calendar.ru/xml/{year}/calendar.xml"

# Ленивая инициализация httpx-клиента (connection reuse)
_httpx_client: Optional[httpx.AsyncClient] = None


_lock = threading.Lock()

def _get_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None or _httpx_client.is_closed:
        with _lock:
            if _httpx_client is None or _httpx_client.is_closed:
                _httpx_client = httpx.AsyncClient(timeout=30.0)
                atexit.register(_cleanup_client)
    return _httpx_client


def _cleanup_client() -> None:
    global _httpx_client
    if _httpx_client is not None and not _httpx_client.is_closed:
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(_httpx_client.aclose())
        except Exception:
            pass
    _httpx_client = None


# ── Загрузка и парсинг XML ─────────────────────────────────────────────────


async def download_calendar_xml(year: int) -> Optional[str]:
    """Загрузить XML календаря за указанный год."""
    url = CALENDAR_XML_URL.format(year=year)
    client = _get_client()
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[CALENDAR] Ошибка загрузки календаря {year}: {e}")
        return None


def parse_calendar_xml(xml_content: str, year: int) -> list[dict]:
    """Разобрать XML и вернуть список дней с признаками."""
    results = []
    try:
        root = etree.fromstring(xml_content.encode("utf-8"))
        days = root.findall(".//day")
        for day_el in days:
            d_str = day_el.get("d")  # Формат: MM.DD
            day_type = day_el.get("t", "0")  # 0=рабочий, 1=выходной, 2=праздник, 3=сокращённый

            if not d_str:
                continue

            try:
                month, day_num = map(int, d_str.split("."))
                day_date = date(year, month, day_num)
            except (ValueError, IndexError):
                continue

            is_holiday = day_type in ("1", "2")
            is_short_day = day_type == "3"

            results.append({
                "day": day_date,
                "is_holiday": is_holiday,
                "is_short_day": is_short_day,
            })
    except Exception as e:
        print(f"[CALENDAR] Ошибка парсинга XML: {e}")

    return results


# ── Fallback: стандартные выходные (СБ/ВС) ─────────────────────────────────


def _generate_default_calendar(year: int) -> list[dict]:
    """Сгенерировать календарь только с СБ/ВС как выходными."""
    results = []
    current = date(year, 1, 1)
    end = date(year, 12, 31)
    while current <= end:
        is_holiday = current.weekday() >= 5  # суббота=5, воскресенье=6
        results.append({
            "day": current,
            "is_holiday": is_holiday,
            "is_short_day": False,
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


async def update_calendar(db: Session, year: int) -> tuple[bool, str]:
    """Полный цикл обновления календаря: загрузка → парсинг → сохранение.
    Если XML-источник недоступен, использует fallback (СБ/ВС)."""
    xml_content = await download_calendar_xml(year)

    if xml_content:
        days_data = parse_calendar_xml(xml_content, year)

    if not xml_content or not days_data:
        print(f"[CALENDAR] Использую fallback-календарь (СБ/ВС) за {year} год")
        days_data = _generate_default_calendar(year)

    if not days_data:
        return False, f"Не удалось сформировать календарь за {year} год"

    save_calendar_to_db(db, year, days_data)
    return True, f"Календарь за {year} год обновлён ({len(days_data)} дней)"


def get_calendar_days(db: Session, year: int) -> list[dict]:
    """Получить все дни календаря за год."""
    cal = db.query(YearCalendar).filter(YearCalendar.year == year).first()
    if not cal:
        return []

    return [
        {
            "day": str(d.day),
            "is_holiday": d.is_holiday,
            "is_short_day": d.is_short_day,
        }
        for d in sorted(cal.days, key=lambda x: x.day)
    ]


def get_month_calendar(db: Session, year: int, month: int) -> dict:
    """Получить календарь на конкретный месяц: кол-во рабочих/выходных/праздничных дней."""
    all_days = get_calendar_days(db, year)

    month_days = [d for d in all_days if d["day"].startswith(f"{year}-{month:02d}")]

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