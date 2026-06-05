from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.calendar_service import (
    get_calendar_days,
    get_month_calendar,
    update_calendar,
)
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/calendar/api", tags=["calendar"])


@router.get("/days")
async def api_calendar_days(
    year: int = Query(default_factory=lambda: date.today().year),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Получить календарь за указанный год."""
    days = get_calendar_days(db, year)
    return {"year": year, "days": days, "count": len(days)}


@router.get("/month")
async def api_calendar_month(
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Статистика по месяцу."""
    return get_month_calendar(db, year, month)


@router.post("/update")
async def api_calendar_update(
    year: int = Form(default_factory=lambda: date.today().year + 1),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Загрузить/обновить производственный календарь за указанный год."""
    await update_calendar(db, year)
    return RedirectResponse(url=f"/calendar?year={year}", status_code=302)
