from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    streaming_stt_model: str = "gpt-4o-mini-transcribe"
    streaming_tts_model: str = "gpt-4o-mini-tts"
    streaming_tts_voice: str = "alloy"
    enable_streaming_voice_experiment: bool = False
    streaming_ws_path: str = "/ws/media-stream"
    streaming_voice_route: str = "/voice-stream"
    max_call_turns: int = 12
    max_llm_calls_per_session: int = 6
    enable_basic_rate_limiting: bool = True
    max_new_calls_per_number_per_hour: int = 5
    google_calendar_enabled: bool = False
    google_calendar_id: str = "primary"
    google_client_secrets_file: str = "./credentials.json"
    google_token_file: str = "./token.json"
    google_oauth_redirect_uri: str = ""
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
