from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class YearCalendar(Base):
    __tablename__ = "year_calendars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    year: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    days = relationship("CalendarDay", back_populates="calendar", cascade="all, delete-orphan", order_by="CalendarDay.day")

    def __repr__(self) -> str:
        return f"<YearCalendar {self.year}>"


class CalendarDay(Base):
    __tablename__ = "calendar_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    calendar_id: Mapped[int] = mapped_column(Integer, ForeignKey("year_calendars.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    is_short_day: Mapped[bool] = mapped_column(Boolean, default=False)

    calendar = relationship("YearCalendar", back_populates="days")

    def __repr__(self) -> str:
        return f"<CalendarDay {self.day} holiday={self.is_holiday}>"