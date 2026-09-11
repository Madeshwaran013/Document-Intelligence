"""
Application entrypoint.

Serves:
  * REST API under /api/v1/*  (see app/api/routes/documents.py)
  * Swagger/OpenAPI docs at /docs (auto, FastAPI default)
  * The static HTML/CSS/JS frontend at /
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.documents import router as documents_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import configure_logging, get_logger
from app.utils.exceptions import DocIntelError

configure_logging()
logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Document Extraction, Validation & API Platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialised. LLM extraction enabled=%s",
                bool(settings.ANTHROPIC_API_KEY) and settings.USE_LLM_EXTRACTION)


app.include_router(documents_router)


@app.exception_handler(DocIntelError)
async def docintel_error_handler(request: Request, exc: DocIntelError):
    logger.warning("DocIntelError: %s", exc.message)
    return JSONResponse(status_code=exc.http_status, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed.",
                            "details": exc.errors()}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected server error occurred."}},
    )


# --- Frontend (static HTML/CSS/JS) ---
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

if _FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR / "static"), name="static")

    @app.get("/")
    def serve_dashboard():
        return FileResponse(_FRONTEND_DIR / "templates" / "dashboard.html")

    @app.get("/document/{document_name}")
    def serve_document_result(document_name: str):
        return FileResponse(_FRONTEND_DIR / "templates" / "document_result.html")
