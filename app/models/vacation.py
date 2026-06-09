from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Vacation(Base):
    __tablename__ = "vacations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="planned", index=True)  # planned, active, completed, cancelled
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    employee = relationship("Employee", back_populates="vacations")

    @property
    def status_label(self) -> str:
        labels = {
            "planned": "📋 Запланирован",
            "active": "🏖️ Активен",
            "completed": "✅ Завершён",
            "cancelled": "❌ Отменён",
        }
        return labels.get(self.status, self.status)

    def __repr__(self) -> str:
        return f"<Vacation {self.start_date} - {self.end_date} ({self.status})>"