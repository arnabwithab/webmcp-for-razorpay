from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 9000
    store_origin: str = "http://localhost:8000"
    agent_origin: str = "http://localhost:8001"
    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str
    max_amount_paise: int = 500000


settings = Settings()
