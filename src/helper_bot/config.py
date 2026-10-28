from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    app_origin: str = "http://127.0.0.1:8000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://helper@127.0.0.1:55432/helper"
