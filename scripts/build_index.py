#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402
from chromadb.utils import embedding_functions  # noqa: E402

from app.tools.rag_tool import CHROMA_PATH, COLLECTION_NAME, EMBEDDING_MODEL  # noqa: E402

KB_DIR = ROOT / "data" / "kb"


def build_index() -> None:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    client.delete_collection(COLLECTION_NAME) if COLLECTION_NAME in [
        c.name for c in client.list_collections()
    ] else None
    collection = client.create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)

    ids, documents, metadatas = [], [], []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text().strip()
        title_line = text.splitlines()[0].lstrip("# ").strip()
        ids.append(path.stem)
        documents.append(text)
        metadatas.append({"title": title_line})

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Indexed {len(ids)} KB docs into {CHROMA_PATH}")


if __name__ == "__main__":
    build_index()
