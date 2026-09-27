"""Absolute project paths shared by Agent and platform modules."""

from __future__ import annotations

import os
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SERVICE_ROOT
DATA_ROOT = Path(
    os.getenv("CHEBALING_DATA_ROOT", str(WORKSPACE_ROOT / "data"))
).expanduser().resolve()
REFERENCE_DATA_DIR = DATA_ROOT / "reference" / "source_data"
KNOWLEDGE_SOURCE_DIR = DATA_ROOT / "reference" / "source_documents"
KNOWLEDGE_CLEAN_DIR = DATA_ROOT / "knowledge" / "clean"
KNOWLEDGE_PROCESSED_DIR = DATA_ROOT / "knowledge" / "processed"
PREDICTION_OUTPUT_DIR = DATA_ROOT / "processed" / "predictions"
