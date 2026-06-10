from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi import status as http_status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/employees", tags=["employees"])


def hx_redirect(url: str, request: Request) -> Response:
    """Редирект с учётом htmx: HX-Redirect для htmx-запросов, 302 для обычных."""
    if request.headers.get("HX-Request"):
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = url
        return response
    return RedirectResponse(url=url, status_code=http_status.HTTP_302_FOUND)


@router.get("/api")
async def api_list_employees(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    employees = db.query(Employee).order_by(Employee.full_name).all()
    return [
        {
            "id": e.id,
            "full_name": e.full_name,
            "position": e.position,
            "department": e.department,
            "annual_days": e.annual_days,
            "carry_over_days": e.carry_over_days,
            "total_days": e.total_days,
            "used_days": e.used_days,
            "remaining_days": e.remaining_days,
            "color": e.color,
            "is_active": e.is_active,
            "vacation_count": len(e.vacations),
        }
        for e in employees
    ]


@router.post("/api")
async def api_create_employee(
    request: Request,
    full_name: str = Form(...),
    position: str = Form(""),
    department: str = Form(""),
    annual_days: int = Form(28),
    carry_over_days: int = Form(0),
    color: str = Form("#3b82f6"),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    employee = Employee(
        full_name=full_name.strip(),
        position=position.strip(),
        department=department.strip(),
        annual_days=annual_days,
        carry_over_days=carry_over_days,
        color=color,
    )
    db.add(employee)
    db.commit()
    return hx_redirect("/employees", request)


@router.get("/api/{employee_id}")
async def api_get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    vacations = []
    for v in employee.vacations:
        vacations.append({
            "id": v.id,
            "start_date": str(v.start_date),
            "end_date": str(v.end_date),
            "days_count": v.days_count,
            "status": v.status,
            "status_label": v.status_label,
            "comment": v.comment,
        })

    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "position": employee.position,
        "department": employee.department,
        "annual_days": employee.annual_days,
        "carry_over_days": employee.carry_over_days,
        "total_days": employee.total_days,
        "used_days": employee.used_days,
        "remaining_days": employee.remaining_days,
        "color": employee.color,
        "is_active": employee.is_active,
        "vacations": vacations,
    }


@router.post("/api/{employee_id}/edit")
async def api_update_employee(
    employee_id: int,
    request: Request,
    full_name: str = Form(...),
    position: str = Form(""),
    department: str = Form(""),
    annual_days: int = Form(28),
    carry_over_days: int = Form(0),
    color: str = Form("#3b82f6"),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    employee.full_name = full_name.strip()
    employee.position = position.strip()
    employee.department = department.strip()
    employee.annual_days = annual_days
    employee.carry_over_days = carry_over_days
    employee.color = color
    employee.is_active = is_active
    db.commit()

    return hx_redirect("/employees", request)


@router.get("/api/{employee_id}/delete")
async def api_delete_employee(
    employee_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    db.delete(employee)
    db.commit()

    return hx_redirect("/employees", request)