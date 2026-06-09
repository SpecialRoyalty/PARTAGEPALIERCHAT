from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    WEBHOOK_BASE_URL: str = ""
    ADMIN_TOKEN: str = "change-me"
    ADMIN_IDS: str = ""
    SECRET_KEY: str = "change-me"
    PORT: int = 8000

    @property
    def admin_ids(self) -> list[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
