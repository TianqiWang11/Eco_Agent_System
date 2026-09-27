from llama_index.core import StorageContext, load_index_from_storage

from src.agent.tools.local_tools.knowledge.config import PERSIST_DIR, apply_knowledge_settings


def get_retriever(top_k: int = 4):
    apply_knowledge_settings()

    storage_context = StorageContext.from_defaults(
        persist_dir=str(PERSIST_DIR)
    )
    index = load_index_from_storage(storage_context)
    return index.as_retriever(similarity_top_k=top_k)