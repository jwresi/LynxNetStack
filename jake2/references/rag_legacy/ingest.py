from pathlib import Path
import hashlib
import json
import os
import requests
import chromadb
from chromadb.config import Settings
import fitz  # pymupdf
from docx import Document
from bs4 import BeautifulSoup
import markdown as md

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = PROJECT_ROOT / "docs"
KB_MANIFEST_PATH = PROJECT_ROOT / "training" / "knowledgebase" / "jake_kb_manifest.json"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "ingest_manifest.json"
COLLECTION_NAME = "jake_docs_v1"


def _repo_env_value(key: str, default: str) -> str:
    value = os.environ.get(key)
    if value:
        return value
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            name, raw = line.split("=", 1)
            if name.strip() == key:
                return raw.strip()
    return default


OLLAMA_URL = _repo_env_value("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/embed"
EMBED_MODEL = _repo_env_value("OLLAMA_EMBED_MODEL", "embeddinggemma")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_pdf(path: Path) -> str:
    doc = fitz.open(path)
    text = []
    for page in doc:
        text.append(page.get_text())
    return "\n".join(text)


def read_docx(path: Path) -> str:
    d = Document(path)
    return "\n".join(p.text for p in d.paragraphs)


def read_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    return soup.get_text("\n")


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".log", ".cfg", ".conf", ".rsc", ".yaml", ".yml", ".json"}:
        return read_text_file(path)
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix == ".docx":
        return read_docx(path)
    if suffix in {".html", ".htm"}:
        return read_html(path)
    return ""


def simple_chunk(text: str, chunk_words: int = 700, overlap_words: int = 100) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(end - overlap_words, start + 1)
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": EMBED_MODEL, "input": texts},
        timeout=300,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embeddings"]


def build_metadata(path: Path, chunk_index: int) -> dict:
    try:
        rel = path.relative_to(PROJECT_ROOT)
    except ValueError:
        rel = path
    parts = rel.parts
    system = parts[1] if len(parts) > 1 else "general"
    return {
        "source_path": str(path),
        "relative_path": str(rel),
        "file_name": path.name,
        "system": system.lower(),
        "doc_type": "unknown",
        "chunk_index": chunk_index,
        "mtime": int(path.stat().st_mtime),
    }


def load_kb_manifest() -> dict[str, dict]:
    if not KB_MANIFEST_PATH.exists():
        return {}
    payload = json.loads(KB_MANIFEST_PATH.read_text())
    records = payload.get("records") or []
    return {str(item.get("relative_path")): item for item in records if item.get("relative_path")}


def iter_ingest_paths(kb_manifest: dict[str, dict]) -> list[Path]:
    paths: list[Path] = []
    if kb_manifest:
        for rel, row in kb_manifest.items():
            if not row.get("include_in_rag"):
                continue
            path = PROJECT_ROOT / rel
            if path.is_file():
                paths.append(path)
        return sorted(paths)

    paths.extend(path for path in DOCS_ROOT.rglob("*") if path.is_file())
    return sorted(paths)


def main() -> None:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    kb_manifest = load_kb_manifest()

    manifest = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())

    for path in iter_ingest_paths(kb_manifest):
        if path.suffix.lower() not in {".md", ".txt", ".log", ".cfg", ".conf", ".rsc", ".yaml", ".yml", ".json", ".pdf", ".docx", ".html", ".htm"}:
            continue

        sha = file_sha256(path)
        if manifest.get(str(path)) == sha:
            continue

        text = extract_text(path).strip()
        if not text:
            continue

        chunks = simple_chunk(text)
        ids, docs, metas = [], [], []
        for i, chunk in enumerate(chunks):
            ids.append(hashlib.sha256(f"{path}:{i}".encode()).hexdigest())
            docs.append(chunk)
            meta = build_metadata(path, i)
            rel = meta["relative_path"]
            if rel in kb_manifest:
                manifest_row = kb_manifest[rel]
                meta["source_class"] = manifest_row.get("source_class", meta.get("doc_type"))
                meta["authoritative"] = bool(manifest_row.get("authoritative"))
            metas.append(meta)

        embeddings = embed_texts(docs)
        collection.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
        manifest[str(path)] = sha
        print(f"Ingested {path} ({len(chunks)} chunks)")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
