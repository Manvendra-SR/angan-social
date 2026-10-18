from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, regardless of the directory the app is started from
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Neon: the direct URL is used for creating tables, the pooled URL
    # (PgBouncer) for the running API. Falls back to the direct URL.
    DATABASE_URL: str
    DATABASE_URL_POOLED: str | None = None
    # Only used by the test suite. Must point at a separate database/branch.
    TEST_DATABASE_URL: str | None = None

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Comma-separated list of frontend origins allowed by CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str
    MAX_IMAGE_SIZE_MB: int = 5

    @property
    def app_database_url(self) -> str:
        return self.DATABASE_URL_POOLED or self.DATABASE_URL

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
