from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi import status as http_status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.vacation import Vacation
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/vacations", tags=["vacations"])


def _calc_workdays(start: date, end: date) -> int:
    """Расчёт рабочих дней между датами (исключая СБ/ВС)."""
    workdays = 0
    current = start
    while current <= end:
        if current.weekday() < 5:  # ПН–ПТ
            workdays += 1
        current += timedelta(days=1)
    return workdays


@router.get("/api/employee/{employee_id}")
async def api_employee_vacations(
    employee_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Список отпусков конкретного сотрудника."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    vacations = (
        db.query(Vacation)
        .filter(Vacation.employee_id == employee_id)
        .order_by(Vacation.start_date.desc())
        .all()
    )

    return [
        {
            "id": v.id,
            "start_date": str(v.start_date),
            "end_date": str(v.end_date),
            "days_count": v.days_count,
            "status": v.status,
            "status_label": v.status_label,
            "comment": v.comment,
            "created_at": str(v.created_at),
        }
        for v in vacations
    ]


@router.post("/api/add")
async def api_add_vacation(
    request: Request,
    employee_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    status: str = Form("planned"),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Добавить новый отпуск сотруднику."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    try:
        s_date = date.fromisoformat(start_date)
        e_date = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты. Ожидается YYYY-MM-DD")

    if e_date < s_date:
        raise HTTPException(status_code=400, detail="Дата окончания раньше даты начала")

    days_count = (e_date - s_date).days + 1

    vacation = Vacation(
        employee_id=employee_id,
        start_date=s_date,
        end_date=e_date,
        days_count=days_count,
        status=status,
        comment=comment.strip(),
    )
    db.add(vacation)
    db.commit()

    redirect_url = f"/employees/{employee_id}"
    return RedirectResponse(url=redirect_url, status_code=http_status.HTTP_302_FOUND)


@router.post("/api/{vacation_id}/edit")
async def api_edit_vacation(
    vacation_id: int,
    request: Request,
    start_date: str = Form(...),
    end_date: str = Form(...),
    status: str = Form("planned"),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Редактировать отпуск (перенос, изменение статуса)."""
    vacation = db.query(Vacation).filter(Vacation.id == vacation_id).first()
    if not vacation:
        raise HTTPException(status_code=404, detail="Отпуск не найден")

    try:
        s_date = date.fromisoformat(start_date)
        e_date = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")

    if e_date < s_date:
        raise HTTPException(status_code=400, detail="Дата окончания раньше даты начала")

    vacation.start_date = s_date
    vacation.end_date = e_date
    vacation.days_count = (e_date - s_date).days + 1
    vacation.status = status
    vacation.comment = comment.strip()
    db.commit()

    redirect_url = f"/employees/{vacation.employee_id}"
    return RedirectResponse(url=redirect_url, status_code=http_status.HTTP_302_FOUND)


@router.get("/api/{vacation_id}/delete")
async def api_delete_vacation(
    vacation_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Удалить отпуск."""
    vacation = db.query(Vacation).filter(Vacation.id == vacation_id).first()
    if not vacation:
        raise HTTPException(status_code=404, detail="Отпуск не найден")

    employee_id = vacation.employee_id
    db.delete(vacation)
    db.commit()

    return RedirectResponse(url=f"/employees/{employee_id}", status_code=http_status.HTTP_302_FOUND)