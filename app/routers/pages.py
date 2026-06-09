from datetime import date, datetime
from collections import defaultdict

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.employee import Employee
from app.models.vacation import Vacation
from app.models.calendar import CalendarDay, YearCalendar
from app.services.calendar_service import get_calendar_days
from app.utils.auth import require_auth_page

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")

# ── Месяцы для отображения ────────────────────────────────────────────────

MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


# ── Страницы ──────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница входа."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    year: int = Query(default_factory=lambda: date.today().year),
    db: Session = Depends(get_db),
):
    """Главная страница — дашборд с диаграммой Ганта."""
    admin, redirect = require_auth_page(request, db)
    if redirect:
        return redirect

    employees = (
        db.query(Employee)
        .filter(Employee.is_active == True)
        .options(selectinload(Employee.vacations))
        .order_by(Employee.full_name)
        .all()
    )

    # Собираем отпуска за выбранный год
    vacations_data = []
    for emp in employees:
        for v in emp.vacations:
            if v.status == "cancelled":
                continue
            # Определяем, попадает ли отпуск в выбранный год
            v_start_year = v.start_date.year
            v_end_year = v.end_date.year

            if v_end_year < year or v_start_year > year:
                continue

            # Обрезаем отображение под год
            display_start = v.start_date
            display_end = v.end_date
            if v_start_year < year:
                display_start = date(year, 1, 1)
            if v_end_year > year:
                display_end = date(year, 12, 31)

            # Вычисляем процентное положение в году
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)
            total_days = (year_end - year_start).days + 1

            left_pct = max(0, (display_start - year_start).days / total_days * 100)
            width_pct = max(1, (display_end - display_start).days / total_days * 100)

            vacations_data.append({
                "id": v.id,
                "employee_id": emp.id,
                "employee_name": emp.full_name,
                "start_date": str(v.start_date),
                "end_date": str(v.end_date),
                "days_count": v.days_count,
                "status": v.status,
                "status_label": v.status_label,
                "left_pct": round(left_pct, 2),
                "width_pct": round(width_pct, 2),
            })

    # Группируем по сотрудникам
    gantt_data = defaultdict(list)
    for vd in vacations_data:
        gantt_data[vd["employee_id"]].append(vd)

    employee_vacations = [
        {
            "id": emp.id,
            "name": emp.full_name,
            "position": emp.position,
            "annual_days": emp.annual_days,
            "used_days": emp.used_days,
            "remaining_days": emp.remaining_days,
            "vacations": gantt_data.get(emp.id, []),
        }
        for emp in employees
    ]

    # Загружаем праздничные дни для календаря
    calendar_days = get_calendar_days(db, year)
    holiday_dates = {d["day"] for d in calendar_days if d["is_holiday"]}

    # Строим сетку выходных/праздников по месяцам
    months_holidays = defaultdict(set)
    for d_str in holiday_dates:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
            months_holidays[d.month].add(d.day)
        except ValueError:
            pass

    # Текущий месяц
    today = date.today()
    current_month = today.month if today.year == year else 1

    # Формируем данные для бокового календаря
    months_data = []
    for m in range(1, 13):
        month_holidays = months_holidays.get(m, set())
        months_data.append({
            "num": m,
            "name": MONTH_NAMES[m],
            "holiday_count": len(month_holidays),
            "is_current": m == current_month,
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "employee_vacations": employee_vacations,
        "months_data": months_data,
        "current_year": year,
        "next_year": year + 1,
        "prev_year": year - 1,
        "today": str(today),
        "month_names": MONTH_NAMES,
    })


@router.get("/employees", response_class=HTMLResponse)
async def employees_page(request: Request, db: Session = Depends(get_db)):
    """Страница списка сотрудников."""
    admin, redirect = require_auth_page(request, db)
    if redirect:
        return redirect

    employees = db.query(Employee).order_by(Employee.full_name).all()
    return templates.TemplateResponse("employees.html", {
        "request": request,
        "employees": [
            {
                "id": e.id,
                "full_name": e.full_name,
                "position": e.position,
                "annual_days": e.annual_days,
                "used_days": e.used_days,
                "remaining_days": e.remaining_days,
                "is_active": e.is_active,
                "vacation_count": len(e.vacations),
            }
            for e in employees
        ],
    })


@router.get("/employees/{employee_id}", response_class=HTMLResponse)
async def employee_detail(
    request: Request,
    employee_id: int,
    db: Session = Depends(get_db),
):
    """Страница деталей сотрудника с его отпусками."""
    admin, redirect = require_auth_page(request, db)
    if redirect:
        return redirect

    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return RedirectResponse(url="/employees", status_code=302)

    vacations = (
        db.query(Vacation)
        .filter(Vacation.employee_id == employee_id)
        .order_by(Vacation.start_date.desc())
        .all()
    )

    return templates.TemplateResponse("employee_detail.html", {
        "request": request,
        "employee": {
            "id": employee.id,
            "full_name": employee.full_name,
            "position": employee.position,
            "annual_days": employee.annual_days,
            "used_days": employee.used_days,
            "remaining_days": employee.remaining_days,
            "is_active": employee.is_active,
        },
        "vacations": [
            {
                "id": v.id,
                "start_date": str(v.start_date),
                "end_date": str(v.end_date),
                "days_count": v.days_count,
                "status": v.status,
                "status_label": v.status_label,
                "comment": v.comment,
            }
            for v in vacations
        ],
        "today": str(date.today()),
    })


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    year: int = Query(default_factory=lambda: date.today().year),
    db: Session = Depends(get_db),
):
    """Страница производственного календаря."""
    admin, redirect = require_auth_page(request, db)
    if redirect:
        return redirect

    calendar_days = get_calendar_days(db, year)
    has_data = len(calendar_days) > 0

    # Группируем по месяцам
    months = defaultdict(list)
    for d in calendar_days:
        try:
            dt = datetime.strptime(d["day"], "%Y-%m-%d").date()
            months[dt.month].append({
                "day": dt.day,
                "is_holiday": d["is_holiday"],
                "is_short_day": d["is_short_day"],
                "weekday": dt.weekday(),
            })
        except ValueError:
            continue

    # Строим календарную сетку по месяцам
    months_data = []
    for m in range(1, 13):
        days = months.get(m, [])
        work_days = sum(1 for d in days if not d["is_holiday"])
        holidays = sum(1 for d in days if d["is_holiday"])
        short = sum(1 for d in days if d["is_short_day"])

        months_data.append({
            "num": m,
            "name": MONTH_NAMES[m],
            "total_days": len(days),
            "work_days": work_days,
            "holidays": holidays,
            "short_days": short,
            "days": days,
        })

    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "year": year,
        "next_year": year + 1,
        "prev_year": year - 1,
        "has_data": has_data,
        "months_data": months_data,
        "month_names": MONTH_NAMES,
    })


# ── PWA ────────────────────────────────────────────────────────────────────

_SW_JS = """const CACHE = "otpysk-v4";

self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  e.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(e.request).then((cached) => {
        const fetched = fetch(e.request).then((response) => {
          if (response.ok) cache.put(e.request, response.clone());
          return response;
        });
        return cached || fetched;
      })
    )
  );
});
"""

_MANIFEST = """{
  "name": "Отпускной",
  "short_name": "Отпускной",
  "description": "Сервис учёта отпусков сотрудников",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#f9fafb",
  "theme_color": "#1e293b",
  "orientation": "any",
  "lang": "ru"
}
"""


@router.get("/sw.js", response_class=PlainTextResponse)
async def service_worker():
    return PlainTextResponse(_SW_JS, media_type="application/javascript")


@router.get("/manifest.json")
async def manifest():
    import json
    return JSONResponse(json.loads(_MANIFEST), media_type="application/manifest+json")
