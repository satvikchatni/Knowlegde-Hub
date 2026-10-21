from pydantic_settings import BaseSettings,SettingsConfigDict
from sqlalchemy import URL
from pydantic import Field
class Settings(BaseSettings):
    

    database_user: str
    database_password: str
    database_host: str
    database_port: int
    database_name: str
    secret_key: str=Field(min_length=32, max_length=128)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    upload_dir : str= "storage"
    max_uplad_mb: int= 10

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