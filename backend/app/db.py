from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_sqlite_compatibility():
    inspector = inspect(engine)
    statements: list[str] = []

    if "call_logs" in inspector.get_table_names():
        call_log_columns = {column["name"] for column in inspector.get_columns("call_logs")}
        if "detected_intent" not in call_log_columns:
            statements.append("ALTER TABLE call_logs ADD COLUMN detected_intent VARCHAR(64)")
        if "intent_data" not in call_log_columns:
            statements.append("ALTER TABLE call_logs ADD COLUMN intent_data TEXT")
        if "business_id" not in call_log_columns:
            statements.append("ALTER TABLE call_logs ADD COLUMN business_id INTEGER")

    if "appointment_requests" in inspector.get_table_names():
        appointment_columns = {column["name"] for column in inspector.get_columns("appointment_requests")}
        if "business_id" not in appointment_columns:
            statements.append("ALTER TABLE appointment_requests ADD COLUMN business_id INTEGER")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
