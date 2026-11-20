from __future__ import annotations

import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
_configured_storage_dir = os.getenv("STORAGE_BASE_DIR", "").strip()
STORAGE_DIR = (
    Path(_configured_storage_dir).expanduser()
    if _configured_storage_dir
    else DATA_DIR
)
if _configured_storage_dir and not STORAGE_DIR.is_absolute():
    STORAGE_DIR = ROOT_DIR / STORAGE_DIR
FRONTEND_DIR = ROOT_DIR / "frontend"
UPLOADS_DIR = STORAGE_DIR / "uploads"
VECTOR_DB_DIR = DATA_DIR / "db"
RAW_SOURCES_DIR = DATA_DIR / "raw_sources"
MANIFESTS_DIR = DATA_DIR / "manifests"
APP_DB_PATH = VECTOR_DB_DIR / "app.db"
DOCS_DIR = DATA_DIR / "Docs"
PDFS_DIR = DATA_DIR / "pdfs"
CASELAW_DIR = DATA_DIR / "CaseLaw"
STATELAWS_DIR = DATA_DIR / "StateLaws"
JSON_DIR = DATA_DIR / "Json"
INTENTS_PATH = JSON_DIR / "Intents.json"
MODEL_DIR = BACKEND_DIR / "Model"
