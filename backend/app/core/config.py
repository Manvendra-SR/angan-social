from pathlib import Path
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, regardless of the directory the app is started from
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# the value shipped in .env.example; never acceptable as a real key
PLACEHOLDER_SECRET_KEY = "change-me-to-a-long-random-string"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    # hide_input_in_errors: a validation error must never print the rejected value
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore", hide_input_in_errors=True)

    # Neon: the direct URL is used for creating tables, the pooled URL
    # (PgBouncer) for the running API. Falls back to the direct URL.
    DATABASE_URL: str
    DATABASE_URL_POOLED: str | None = None
    # Only used by the test suite. Must point at a separate database/branch.
    TEST_DATABASE_URL: str | None = None

    # SecretStr: shows as '**********' if settings are ever printed or logged
    SECRET_KEY: SecretStr
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Comma-separated list of frontend origins allowed by CORS (and the WebSocket)
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: SecretStr
    MAX_IMAGE_SIZE_MB: int = 5

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_is_strong(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value()
        if len(key) < MIN_SECRET_KEY_LENGTH or key == PLACEHOLDER_SECRET_KEY:
            raise ValueError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters "
                "and must not be the example value"
            )
        return value

    @property
    def app_database_url(self) -> str:
        return self.DATABASE_URL_POOLED or self.DATABASE_URL

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
