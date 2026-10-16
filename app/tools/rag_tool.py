import os
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

ROOT = Path(__file__).resolve().parents[2]
CHROMA_PATH = Path(os.environ.get("CHROMA_PATH", ROOT / "data" / "chroma_data"))
COLLECTION_NAME = "kb_docs"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME, embedding_function=embed_fn
    )


def search_kb(query: str, top_k: int = 3) -> list[dict]:
    collection = _get_collection()
    if collection.count() == 0:
        return []

    results = collection.query(query_texts=[query], n_results=min(top_k, collection.count()))

    snippets = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
        snippets.append(
            {
                "doc_id": doc_id,
                "title": metadata.get("title", doc_id),
                "text": text,
                "score": 1.0 - distance,
            }
        )
    return snippets
