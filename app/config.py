from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    VERSION: str = "0.1.0"
    PROJECT_NAME: str = "krishora-insight"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5437/krishora"
    CORE_AUTH_SECRET_KEY: str = ""
    CORE_JWT_ALGORITHM: str = "HS256"
    CORE_API_URL: str = "https://api-dev-core.rattanshanti.org"
    CORE_MEMBERSHIP_CACHE_TTL: float = 45.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
