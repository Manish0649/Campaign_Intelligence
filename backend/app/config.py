import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Settings(BaseModel):
    app_name: str = "Campaign Intelligence API"
    environment: str = os.getenv("ENVIRONMENT", "development")
    port: int = int(os.getenv("PORT", "8000"))

    database_url: str = os.getenv("DATABASE_URL", "")

    data_dir: Path = BASE_DIR / "data"
    processed_dir: Path = BASE_DIR / "data" / "processed" / "clean_db_ready"
    forecast_dir: Path = BASE_DIR / "data" / "forecast"

    default_forecast_horizon_days: int = 7
    safety_stock_z_score: float = 1.65
    inventory_staleness_hours: int = 72
    max_campaign_products: int = 2
    default_target_audience_size: int = 5000

    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_algorithm: str = "HS256"
    jwt_exp_seconds: int = int(os.getenv("JWT_EXP_SECONDS", "3600"))
    jwt_issuer: str = os.getenv("JWT_ISSUER", "campaign-intelligence")
    jwt_audience: str = os.getenv("JWT_AUDIENCE", "campaign-intelligence-api")

    admin_email: str = os.getenv("ADMIN_EMAIL", "")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    admin_role: str = os.getenv("ADMIN_ROLE", "SYS-ADMIN")
    auth_users_json: str = os.getenv("AUTH_USERS_JSON", "")
    proposal_user_email: str = os.getenv("PROPOSAL_USER_EMAIL", "")
    proposal_user_password: str = os.getenv("PROPOSAL_USER_PASSWORD", "")

    zilliz_endpoint: str = os.getenv("ZILLIZ_ENDPOINT", "")
    zilliz_token: str = os.getenv("ZILLIZ_TOKEN", "")
    zilliz_collection: str = os.getenv("ZILLIZ_COLLECTION", "campaign_intelligence_kb")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_generation_model: str = os.getenv("GEMINI_GENERATION_MODEL", "gemini-3.5-flash-lite")


settings = Settings()
