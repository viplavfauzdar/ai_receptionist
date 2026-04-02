from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    google_calendar_enabled: bool = False
    google_calendar_id: str = "primary"
    google_client_secrets_file: str = "./credentials.json"
    google_token_file: str = "./token.json"
    google_timezone: str = "America/New_York"
    appointment_duration_minutes: int = 30
    twilio_auth_token: str = ""
    disable_twilio_signature_validation: bool = False
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "sqlite:///./receptionist.db"
    business_name: str = "Bright Smile Dental"
    business_greeting: str = "Hello, thanks for calling Bright Smile Dental. How can I help you today?"
    business_hours: str = "Mon-Fri 9 AM to 5 PM"
    booking_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
