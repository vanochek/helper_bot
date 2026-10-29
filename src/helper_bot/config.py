from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ai_mode: Literal["demo", "openai", "groq"] = "demo"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-120b"
    groq_stt_model: str = "whisper-large-v3-turbo"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    openai_stt_model: str = ""
    app_origin: str = "http://127.0.0.1:8000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://helper@127.0.0.1:55432/helper"
