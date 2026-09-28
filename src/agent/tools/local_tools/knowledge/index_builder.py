import chromadb
from pathlib import Path
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from src.agent.tools.local_tools.knowledge.config import (
    KNOWLEDGE_DIR,
    PERSIST_DIR,
    COLLECTION_NAME,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    apply_knowledge_settings,
)


def build_index():
    apply_knowledge_settings()

    documents = SimpleDirectoryReader(str(KNOWLEDGE_DIR)).load_data()

    splitter = SentenceSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    nodes = splitter.get_nodes_from_documents(documents)

    for node in nodes:
        metadata = node.metadata or {}
        file_path = metadata.get("file_path", "")
        node.metadata = {
            **metadata,
            "source_name": Path(file_path).stem if file_path else "unknown",
        }

    PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    if any(getattr(item, "name", item) == COLLECTION_NAME for item in client.list_collections()):
        client.delete_collection(COLLECTION_NAME)
    collection = client.get_or_create_collection(COLLECTION_NAME, embedding_function=None)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex(nodes, storage_context=storage_context, show_progress=True)
    return index


if __name__ == "__main__":
    build_index()
    print("Knowledge index built successfully.")
