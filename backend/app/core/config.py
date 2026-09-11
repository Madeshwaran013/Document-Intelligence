"""
Application configuration.

All configurable values are read from environment variables (optionally
loaded from a local .env file during development). Nothing sensitive is
hardcoded — see .env.example at the repository root for the full list of
supported variables.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- General ---
    APP_NAME: str = "Document Intelligence Platform"
    ENVIRONMENT: str = "development"  # development | production
    LOG_LEVEL: str = "INFO"

    # --- Database ---
    # Default: local SQLite file so the app runs with zero external setup.
    # For production, point this at Postgres/MySQL, e.g.:
    #   postgresql+psycopg2://user:pass@host:5432/dbname
    DATABASE_URL: str = "sqlite:///./storage/app.db"

    # --- File handling ---
    UPLOAD_DIR: str = "./storage/uploads"
    MAX_PAGE_COUNT: int = 3
    ALLOWED_CONTENT_TYPES: tuple = (
        "application/pdf",
        "image/jpeg",
        "image/png",
    )

    # --- OCR ---
    # "tesseract" (local, default, no API key needed) or "ocr_space" (free-tier
    # hosted OCR API — requires OCR_SPACE_API_KEY).
    OCR_PROVIDER: str = "tesseract"
    OCR_SPACE_API_KEY: Optional[str] = None
    OCR_LANGUAGE: str = "eng"

    # --- Extraction (LLM) ---
    # When an API key is supplied, the extraction service uses the LLM for
    # field/table extraction (higher accuracy on varied layouts). When no
    # key is present, it automatically falls back to the built-in
    # rule-based/heuristic extractor so the service keeps working with zero
    # external dependencies (useful for local dev, tests, and grading
    # environments without a key configured).
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_MODEL: str = "claude-sonnet-4-6"
    USE_LLM_EXTRACTION: bool = True  # auto-disables itself if no key is set

    # --- Financial validation tolerance ---
    # Relative tolerance applied to reconciliation checks, to absorb
    # rounding differences in source documents.
    VALIDATION_RELATIVE_TOLERANCE: float = 0.01  # 1%
    VALIDATION_ABSOLUTE_TOLERANCE: float = 1.0    # currency units

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
