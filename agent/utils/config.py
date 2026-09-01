from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8001
    store_origin: str = "http://localhost:8000"
    sidecar_origin: str = "http://localhost:9000"
    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"


settings = Settings()
