import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.db.session import engine, Base
from backend.app.db.migrations import run_compatibility_migrations
from backend.app.api.routes import health, forecasts, feasibility, proposals, decision, auth, knowledge_base
from backend.app.security.auth import validate_security_settings
from backend.app.security.sanitizer import sanitize_log_message
from backend.app.data_bootstrap import download_m5_dataset

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("campaign_intelligence")

is_production = settings.environment.lower() == "production"
app = FastAPI(
    title=settings.app_name,
    description="Deterministic campaign feasibility, demand and supply planning API.",
    version="1.3.0",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

# CORS Middleware
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8501").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health.router)
app.include_router(forecasts.router)
app.include_router(feasibility.router)
app.include_router(proposals.router)
app.include_router(decision.router)
app.include_router(auth.router)
app.include_router(knowledge_base.router)


@app.on_event("startup")
def on_startup():
    logger.info(f"Starting {settings.app_name} in [{settings.environment}] mode.")

    validate_security_settings()

    # Download required forecasting dataset
    try:
        download_m5_dataset()
        logger.info("M5 forecasting dataset is ready.")
    except Exception:
        logger.exception("M5 forecasting dataset initialization failed.")
        raise

    try:
        # Create database tables if not existing
        Base.metadata.create_all(bind=engine)
        run_compatibility_migrations(engine)
        logger.info(
            "Database schemas initialized and additive compatibility migrations applied."
        )
    except Exception as e:
        logger.warning(
            "Database schema initialization failed: %s",
            sanitize_log_message(str(e))
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=settings.port, reload=True)

