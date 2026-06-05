import asyncio
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.database import Base, SessionLocal, engine
from app.models.admin import Admin
from app.routers import auth as auth_router
from app.routers import employees as employees_router
from app.routers import vacations as vacations_router
from app.routers import calendar as calendar_router
from app.routers import pages as pages_router
from app.utils.auth import get_password_hash


def init_db() -> None:
    """Создать таблицы и администратора по умолчанию."""
    from app.config import settings
    import os

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    abs_path = os.path.abspath(db_path)
    db_exists = os.path.exists(abs_path)
    db_size = os.path.getsize(abs_path) if db_exists else 0

    print(f"[INIT] DATABASE_URL={settings.DATABASE_URL}")
    print(f"[INIT] Абсолютный путь: {abs_path}")
    print(f"[INIT] БД существует: {db_exists}, размер: {db_size} байт")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        from app.models.employee import Employee
        emp_count = db.query(Employee).count()
        print(f"[INIT] Сотрудников в БД: {emp_count}")

        admin = db.query(Admin).first()

        # Если ADMIN_PASSWORD задан — хешируем и обновляем пароль админа
        raw_password = os.environ.get("ADMIN_PASSWORD", "")
        print(f"[INIT] ADMIN_PASSWORD из env: '{raw_password}'")
        print(f"[INIT] ADMIN_LOGIN из settings: '{settings.ADMIN_LOGIN}'")
        password = raw_password.strip()
        if password:
            hashed = get_password_hash(password)
            if admin:
                admin.login = settings.ADMIN_LOGIN
                admin.password_hash = hashed
                db.commit()
                print(f"[INIT] Администратор обновлён: {settings.ADMIN_LOGIN}")
            else:
                admin = Admin(
                    login=settings.ADMIN_LOGIN,
                    password_hash=hashed,
                )
                db.add(admin)
                db.commit()
                print(f"[INIT] Создан администратор: {settings.ADMIN_LOGIN}")
            # Удаляем пароль из переменных окружения после использования
            os.environ.pop("ADMIN_PASSWORD", None)
        elif not admin:
            default_admin = Admin(
                login="admin",
                password_hash=get_password_hash("admin"),
            )
            db.add(default_admin)
            db.commit()
            print("[INIT] Создан администратор по умолчанию: admin / admin")
        else:
            print(f"[INIT] Администратор уже существует: {admin.login}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: инициализация БД до приёма соединений."""
    import sys
    sys.stdout.flush()
    try:
        await asyncio.to_thread(init_db)
    except Exception as e:
        print(f"[INIT] ОШИБКА: {e}", flush=True)
        import traceback
        traceback.print_exc()
    sys.stdout.flush()
    yield


def create_app() -> FastAPI:
    limiter = Limiter(key_func=get_remote_address, default_limits=["20/minute"])
    app = FastAPI(
        title="Отпускной",
        description="Сервис учёта отпусков сотрудников",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.include_router(auth_router.router)
    app.include_router(employees_router.router)
    app.include_router(vacations_router.router)
    app.include_router(calendar_router.router)
    app.include_router(pages_router.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "date": str(date.today())}

    return app


app = create_app()