from sqlmodel import SQLModel, create_engine, Session
import os

# Prefer the configured Postgres URL; fall back to local SQLite for development
DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.getenv("USER_DB_PATH", "processed_data/users.db")

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, echo=False)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def init_db():
    if DATABASE_URL:
        SQLModel.metadata.create_all(engine)
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)
