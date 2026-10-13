from pydantic_settings import BaseSettings,SettingsConfigDict
from sqlalchemy import URL
class Settings(BaseSettings):
    

    database_user: str
    database_password: str
    database_host: str
    database_port: int
    database_name: str

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.database_user,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()