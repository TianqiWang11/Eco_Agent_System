# Local Tools: business computation/retrieval, without agent orchestration.
"""Knowledge retrieval only. Answer generation belongs to the Harness."""
def retrieve_knowledge(query: str, top_k: int = 4) -> dict:
    """
    从知识索引检索与问题最相关的文本片段。

    Returns:
        包含来源列表、逐片段结果和拼接后的上下文文本。
    """
    from src.agent.tools.local_tools.knowledge.query_engine import get_retriever
    nodes = get_retriever(top_k=top_k).retrieve(query)
    if not nodes:
        return {
            "sources": [],
            "results": [],
            "context_text": "",
        }

    results = []
    source_names = []

    for node_with_score in nodes[:top_k]:
        node = node_with_score.node
        text = node.get_content()
        source = (node.metadata or {}).get("source_name", "unknown")
        source_names.append(source)
        results.append(
            {
                "source": source,
                "chunk_id": getattr(node, "node_id", None),
                "score": float(node_with_score.score) if node_with_score.score is not None else None,
                "text": text,
            }
        )

    source_names = list(dict.fromkeys(source_names))

    context_text = "\n\n".join(
        [f"[来源: {item['source']}]\n{item['text']}" for item in results]
    )

    return {
        "sources": source_names,
        "results": results,
        "context_text": context_text,
    }
