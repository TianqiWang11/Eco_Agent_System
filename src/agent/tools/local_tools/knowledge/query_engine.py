import chromadb
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore

from src.agent.tools.local_tools.knowledge.config import COLLECTION_NAME, PERSIST_DIR, apply_knowledge_settings


def get_retriever(top_k: int = 4):
    apply_knowledge_settings()

    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    collection = client.get_collection(COLLECTION_NAME, embedding_function=None)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(vector_store)
    return index.as_retriever(similarity_top_k=top_k)
