from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.admin import Admin

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_token_from_cookie(request: Request) -> Optional[str]:
    return request.cookies.get("access_token")


async def get_current_admin(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
) -> Admin:
    """Получить текущего админа из куки или Bearer-токена."""
    if token is None:
        token = get_token_from_cookie(request)

    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        admin_login: Optional[str] = payload.get("sub")
        if admin_login is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен")

    admin = db.query(Admin).filter(Admin.login == admin_login).first()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Админ не найден")

    return admin


def require_auth_page(request: Request, db: Session):
    """Проверка авторизации для HTML-страниц. Возвращает админа или редирект."""
    token = get_token_from_cookie(request)
    if not token:
        return None, RedirectResponse(url="/login", status_code=302)

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        admin_login = payload.get("sub")
        if not admin_login:
            return None, RedirectResponse(url="/login", status_code=302)
    except JWTError:
        return None, RedirectResponse(url="/login", status_code=302)

    admin = db.query(Admin).filter(Admin.login == admin_login).first()
    if not admin:
        return None, RedirectResponse(url="/login", status_code=302)

    return admin, None