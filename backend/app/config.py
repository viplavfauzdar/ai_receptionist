from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    business_name: str = "Bright Smile Dental"
    business_greeting: str = "Hello, thanks for calling Bright Smile Dental. How can I help you today?"
    business_hours: str = "Mon-Fri 9 AM to 5 PM"
    booking_enabled: bool = True
    database_url: str = "sqlite:///./receptionist.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
