from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _normalize_phone_number(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(char for char in value.strip() if char.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def ensure_sqlite_compatibility():
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    statements: list[str] = []

    if "call_logs" in table_names:
        call_log_columns = {column["name"] for column in inspector.get_columns("call_logs")}
        if "detected_intent" not in call_log_columns:
            statements.append("ALTER TABLE call_logs ADD COLUMN detected_intent VARCHAR(64)")
        if "intent_data" not in call_log_columns:
            statements.append("ALTER TABLE call_logs ADD COLUMN intent_data TEXT")
        if "business_id" not in call_log_columns:
            statements.append("ALTER TABLE call_logs ADD COLUMN business_id INTEGER")
        if "protection_reason" not in call_log_columns:
            statements.append("ALTER TABLE call_logs ADD COLUMN protection_reason VARCHAR(64)")

    if "call_sessions" in table_names:
        session_columns = {column["name"] for column in inspector.get_columns("call_sessions")}
        if "turn_count" not in session_columns:
            statements.append("ALTER TABLE call_sessions ADD COLUMN turn_count INTEGER DEFAULT 0")
        if "llm_call_count" not in session_columns:
            statements.append("ALTER TABLE call_sessions ADD COLUMN llm_call_count INTEGER DEFAULT 0")
        if "last_protection_reason" not in session_columns:
            statements.append("ALTER TABLE call_sessions ADD COLUMN last_protection_reason VARCHAR(64)")

    if "appointment_requests" in table_names:
        appointment_columns = {column["name"] for column in inspector.get_columns("appointment_requests")}
        if "business_id" not in appointment_columns:
            statements.append("ALTER TABLE appointment_requests ADD COLUMN business_id INTEGER")
        if "calendar_event_id" not in appointment_columns:
            statements.append("ALTER TABLE appointment_requests ADD COLUMN calendar_event_id VARCHAR(255)")
        if "calendar_event_link" not in appointment_columns:
            statements.append("ALTER TABLE appointment_requests ADD COLUMN calendar_event_link TEXT")
        if "scheduled_start" not in appointment_columns:
            statements.append("ALTER TABLE appointment_requests ADD COLUMN scheduled_start DATETIME")
        if "scheduled_end" not in appointment_columns:
            statements.append("ALTER TABLE appointment_requests ADD COLUMN scheduled_end DATETIME")

    if "businesses" in table_names:
        business_columns = {column["name"] for column in inspector.get_columns("businesses")}
        if "twilio_number_normalized" not in business_columns:
            statements.append("ALTER TABLE businesses ADD COLUMN twilio_number_normalized VARCHAR(32)")
        if "google_calendar_connected" not in business_columns:
            statements.append("ALTER TABLE businesses ADD COLUMN google_calendar_connected BOOLEAN DEFAULT 0")
        if "google_account_email" not in business_columns:
            statements.append("ALTER TABLE businesses ADD COLUMN google_account_email VARCHAR(255)")
        if "google_calendar_id" not in business_columns:
            statements.append("ALTER TABLE businesses ADD COLUMN google_calendar_id VARCHAR(255)")
        if "google_token_json" not in business_columns:
            statements.append("ALTER TABLE businesses ADD COLUMN google_token_json TEXT")

    if not statements:
        if "businesses" in table_names:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_businesses_twilio_number_normalized "
                        "ON businesses (twilio_number_normalized)"
                    )
                )
            _backfill_business_phone_normalization()
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        if "businesses" in table_names:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_businesses_twilio_number_normalized "
                    "ON businesses (twilio_number_normalized)"
                )
            )

    if "businesses" in table_names:
        _backfill_business_phone_normalization()


def _backfill_business_phone_normalization() -> None:
    inspector = inspect(engine)
    if "businesses" not in inspector.get_table_names():
        return
    business_columns = {column["name"] for column in inspector.get_columns("businesses")}
    if "twilio_number_normalized" not in business_columns:
        return

    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT id, twilio_number, twilio_number_normalized FROM businesses")
        ).mappings()
        for row in rows:
            normalized = _normalize_phone_number(row["twilio_number"])
            if normalized and row["twilio_number_normalized"] != normalized:
                connection.execute(
                    text(
                        "UPDATE businesses SET twilio_number_normalized = :normalized WHERE id = :business_id"
                    ),
                    {"normalized": normalized, "business_id": row["id"]},
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
