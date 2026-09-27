from shutil import rmtree
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from src.agent.tools.local_tools.knowledge.config import (
    KNOWLEDGE_DIR,
    PERSIST_DIR,
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
            "source_name": file_path.split("/")[-1].replace(".md", "") if file_path else "unknown",
        }

    if PERSIST_DIR.exists():
        rmtree(PERSIST_DIR)

    index = VectorStoreIndex(nodes, show_progress=True)
    index.storage_context.persist(persist_dir=str(PERSIST_DIR))
    return index


if __name__ == "__main__":
    build_index()
    print("Knowledge index built successfully.")