from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_call_log_columns():
    inspector = inspect(engine)
    if "call_logs" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("call_logs")}
    statements: list[str] = []

    if "detected_intent" not in existing_columns:
        statements.append("ALTER TABLE call_logs ADD COLUMN detected_intent VARCHAR(64)")
    if "intent_data" not in existing_columns:
        statements.append("ALTER TABLE call_logs ADD COLUMN intent_data TEXT")

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
