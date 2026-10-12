from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
    

    database_user: str
    database_password: str
    database_host: str
    database_port: int
    database_name: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()