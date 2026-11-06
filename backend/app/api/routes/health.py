import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.app.config import settings
from backend.app.db.session import verify_database_connection
from backend.app.security.auth import get_current_user, require_roles

router = APIRouter(tags=["Health"])
PROJECT_ROOT = Path(__file__).resolve().parents[4]


@router.get("/health")
def health_check():
    """Liveness endpoint: confirms the API process is responding."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": "1.3.0",
    }


@router.get("/health/ready")
def readiness_check():
    """Readiness endpoint: verifies the configured SQL database is reachable."""
    try:
        verify_database_connection()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from exc
    return {"status": "ready", "service": settings.app_name, "database": "connected"}


@router.get("/health/components")
def component_health(current_user: dict = Depends(get_current_user)):
    """Report backend, database, LangGraph, Laya, MCP and external-service status."""
    checks = {}

    checks["backend"] = {"status": "healthy", "detail": "API process is responding"}
    try:
        verify_database_connection()
        checks["database"] = {"status": "healthy", "detail": "SQL database connection succeeded"}
    except RuntimeError:
        checks["database"] = {"status": "unhealthy", "detail": "SQL database connection failed"}

    try:
        from backend.app.agents.graph import campaign_agent_graph
        checks["agents"] = {
            "status": "healthy" if campaign_agent_graph is not None else "unhealthy",
            "detail": "3-stage LangGraph workflow compiled" if campaign_agent_graph is not None else "Graph unavailable",
        }
    except Exception as exc:
        checks["agents"] = {"status": "unhealthy", "detail": f"Agent workflow unavailable ({type(exc).__name__})"}

    try:
        import laya
        checks["laya"] = {"status": "healthy", "detail": f"Python package loaded (v{getattr(laya, '__version__', 'unknown')})"}
    except Exception as exc:
        checks["laya"] = {"status": "unhealthy", "detail": f"Laya package unavailable ({type(exc).__name__})"}

    checks["mcp"] = {
        "status": "healthy" if importlib.util.find_spec("fastmcp") else "unhealthy",
        "detail": "FastMCP SDK installed; run `python -m backend.app.mcp_server` as a separate stdio server"
                  if importlib.util.find_spec("fastmcp") else "FastMCP SDK is not installed",
    }

    checks["gemini"] = {
        "status": "configured" if settings.gemini_api_key else "unconfigured",
        "detail": "API key configured" if settings.gemini_api_key else "GEMINI_API_KEY is missing",
    }

    if settings.zilliz_endpoint and settings.zilliz_token:
        try:
            from knowledge_base.zilliz_client import test_connection
            ok, detail = test_connection()
            checks["zilliz"] = {"status": "healthy" if ok else "unhealthy", "detail": "Collection service reachable" if ok else detail}
        except Exception as exc:
            checks["zilliz"] = {"status": "unhealthy", "detail": f"Zilliz check failed ({type(exc).__name__})"}
    else:
        checks["zilliz"] = {"status": "unconfigured", "detail": "ZILLIZ_ENDPOINT or ZILLIZ_TOKEN is missing"}

    overall = "healthy" if all(item["status"] in {"healthy", "configured"} for item in checks.values()) else "degraded"
    return {"status": overall, "components": checks}


@router.get("/health/tests")
def run_pytest_suite(current_user: dict = Depends(require_roles("SYS-ADMIN"))):
    """Run the project's pytest suite on demand; admin-only to avoid arbitrary load."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short", "--ignore=tests/test_gemini.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "TESTING": "1", "ENVIRONMENT": "testing"},
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Pytest run exceeded the 180-second limit.")
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Could not start pytest.") from exc

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    summary = output.strip().splitlines()[-1] if output.strip() else "No pytest output."
    counts = {key: 0 for key in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed")}
    for amount, label in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)", output):
        normalized = "errors" if label in {"error", "errors"} else label
        if normalized in counts:
            counts[normalized] += int(amount)
    return {
        "exit_code": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "counts": counts,
        "summary": summary,
        "output": output[-12000:],
    }
