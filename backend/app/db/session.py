
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.app.config import settings


Base = declarative_base()


def _is_truthy(value):
    return (value or "").strip().lower() in {"1", "true", "yes"}


# SQLite is allowed only when explicitly enabled.
USE_SQLITE = (
    _is_truthy(os.getenv("TESTING"))
    or _is_truthy(os.getenv("USE_SQLITE"))
)

if settings.environment.lower() == "production" and USE_SQLITE:
    raise RuntimeError("SQLite cannot be enabled in production; configure PostgreSQL/NeonDB.")

if USE_SQLITE:
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    sqlite_path = settings.data_dir / "campaign_intelligence_test.db"
    database_url = f"sqlite:///{sqlite_path}"

    engine = create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )

else:
    database_url = settings.database_url.strip()

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Set your NeonDB connection string in the .env file."
        )

    # Normalize PostgreSQL connection URL.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg2://",
            1,
        )

    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1,
        )

    if not database_url.startswith("postgresql+psycopg2://"):
        raise RuntimeError(
            "Production database must use PostgreSQL. "
            "SQLite is allowed only with TESTING=true "
            "or USE_SQLITE=true."
        )

    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
        connect_args={"connect_timeout": 10},
    )


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def verify_database_connection():
    """
    Verify that the configured database is reachable.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return True

    except Exception as exc:
        raise RuntimeError(
            "Database connection failed. "
            "Check DATABASE_URL and NeonDB availability."
        ) from exc


def get_db():
    """
    FastAPI database session dependency.
    """
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
