from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from src.project_paths import KNOWLEDGE_CLEAN_DIR, SERVICE_ROOT

KNOWLEDGE_DIR = KNOWLEDGE_CLEAN_DIR
PERSIST_DIR = SERVICE_ROOT / "storage" / "chroma"
COLLECTION_NAME = "eco_knowledge"

EMBED_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DEFAULT_TOP_K = 4

CHUNK_SIZE = 500
CHUNK_OVERLAP = 80


def apply_knowledge_settings():
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)
