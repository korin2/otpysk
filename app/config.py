from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "super-secret-key-change-in-production"
    DATABASE_URL: str = "sqlite:///./data/otpysk.db"
    ADMIN_LOGIN: str = "admin"
    ADMIN_PASSWORD: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync driver for Alembic."""
        return self.DATABASE_URL.replace("sqlite:///", "sqlite:///")

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()