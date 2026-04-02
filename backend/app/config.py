from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    database_url: str = "sqlite:///./receptionist.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
