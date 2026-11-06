from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    database_user: str
    database_password: str
    database_host: str
    database_port: int
    database_name: str
    secret_key: str = Field(min_length=32, max_length=128)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    upload_dir: str = "storage"
    max_upload_mb: int = 10
    chunk_size: int = 1000
    chunk_overlap: int = 150
    embedding_batch_size: int = 32
    expected_dimension_size: int = 384

    # app refuses to start if below functions condition is False
    @model_validator(
        mode="after"
    )  # tells pydantic once you have done reading all the raw strings in .env and have converted them to integers, immediately run this function below.
    def check_overlap_less_than_size(self) -> Self:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap has to be smaller than chunk size.")
        return self  # self(the validated instance) must be returned

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
