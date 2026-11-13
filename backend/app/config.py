from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://luke:luke@localhost:5432/lukes_diner"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"
    cors_origins: str = "http://localhost:3000"
    auto_seed: bool = True


settings = Settings()
