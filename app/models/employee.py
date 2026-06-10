from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(255), default="")
    department: Mapped[str] = mapped_column(String(255), default="")
    annual_days: Mapped[int] = mapped_column(Integer, default=28)
    carry_over_days: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(7), default="#3b82f6")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    vacations = relationship("Vacation", back_populates="employee", cascade="all, delete-orphan")

    @property
    def used_days(self) -> int:
        """Сумма дней по всем отпускам (planned + active + completed)."""
        if not self.vacations:
            return 0
        return sum(v.days_count for v in self.vacations if v.status != "cancelled")

    @property
    def total_days(self) -> int:
        """Общий лимит с учётом переноса."""
        return self.annual_days + self.carry_over_days

    @property
    def remaining_days(self) -> int:
        """Остаток дней отпуска с учётом переноса."""
        return max(0, self.total_days - self.used_days)

    def __repr__(self) -> str:
        return f"<Employee {self.full_name}>"
