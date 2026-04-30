from pathlib import Path
import re
import os
import sys
import requests
import chromadb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Legacy note: old Jake prepended PROJECT_ROOT to the import path here.
# Jake2 preserves this file as reference material only and does not execute it.

from jake_shared import SITE_ALIAS_MAP, SITE_SERVICE_PROFILES

CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"
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


def embed_query(text: str) -> list[float]:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": EMBED_MODEL, "input": text},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    embeddings = data.get("embeddings", [])
    if not embeddings:
        raise RuntimeError("Ollama returned no embeddings.")
    return embeddings[0]


def detect_system_filter(query: str):
    q = query.lower()

    if any(x in q for x in [
        "mikrotik", "routeros", "pppoe", "bridge", "vlan",
        "br-cgnat", "dhcp", "splynx", "reject_1", "splbl_blocked"
    ]):
        return "mikrotik"

    if "vilo" in q:
        return "controllers"

    return None


def infer_site_context(query: str):
    site_id = extract_site_id(query)
    aliases: list[str] = []
    q = query.lower()
    if site_id and site_id in SITE_SERVICE_PROFILES:
        aliases.extend([str(alias).lower() for alias in SITE_SERVICE_PROFILES[site_id].get("aliases", []) if alias])
    for alias, alias_site_id in SITE_ALIAS_MAP.items():
        if alias in q:
            if not site_id:
                site_id = alias_site_id
            aliases.append(alias.lower())
    aliases = sorted({alias for alias in aliases if alias})
    return site_id, aliases


def detect_query_class(query: str) -> str:
    q = query.lower()
    if any(token in q for token in ("show ipv4 neighbors", "remote commands", "cnwave controller", "controller", "api", "neighbors")):
        return "controller"
    if any(token in q for token in ("how do i", "how do we", "what should i check", "walk me through", "troubleshoot", "procedure", "process", "best practice", "why does")):
        return "procedure"
    if any(token in q for token in ("site", "building", "pon", "olt", "euclid", "longwood", "savoy", "cambridge", "nycha", "fenimore")):
        return "site"
    if any(token in q for token in ("cpe", "hc220", "vilo", "subscriber", "customer", "unit")):
        return "subscriber"
    return "general"


def extract_site_id(query: str):
    m = re.search(r"\b\d{6}\b", query)
    return m.group(0) if m else None


def tokenize_query(query: str):
    return [t for t in re.split(r"[^a-zA-Z0-9_\-\.]+", query.lower()) if t]


def keyword_boost(doc, meta, query):
    score = 0
    q = query.lower()
    doc_l = doc.lower()
    path_l = meta.get("relative_path", "").lower()
    source_class = str(meta.get("source_class") or "").lower()
    authoritative = bool(meta.get("authoritative"))
    site_id, aliases = infer_site_context(query)
    query_class = detect_query_class(query)

    for term in tokenize_query(q):
        if term in doc_l:
            score += 0.2
        if term in path_l:
            score += 0.3

    if site_id:
        if site_id in doc:
            score += 1
        if site_id in path_l:
            score += 1.5
        if "site_doc" == source_class:
            score += 0.5
    for alias in aliases:
        if alias in doc_l:
            score += 0.4
        if alias in path_l:
            score += 0.7

    if "topology" in q and path_l.startswith("sites/"):
        score += 0.8

    if "rogue" in q and "dhcp" in q:
        if "training" in path_l:
            score += 0.6
        if "savoy" in path_l:
            score -= 0.4

    if authoritative:
        score += 0.15

    if query_class == "site":
        if source_class in {"site_doc", "field_notes"}:
            score += 1.1
        elif source_class in {"controller_doc", "runbook", "reference"}:
            score += 0.2
        elif source_class in {"jake_doc", "training_corpus", "repo_doc"}:
            score -= 0.6

    if query_class == "controller":
        if source_class == "controller_doc":
            score += 1.2
        elif source_class in {"reference", "runbook"}:
            score += 0.5
        elif source_class in {"site_doc", "field_notes"}:
            score += 0.3
        elif source_class in {"training_corpus"}:
            score -= 0.8
        if "cnwave" in q and "cnwave" in path_l:
            score += 1.0
        if "neighbors" in q and ("controller" in path_l or "cnwave" in path_l):
            score += 0.8

    if query_class == "procedure":
        if source_class in {"controller_doc", "runbook", "reference"}:
            score += 0.9
        elif source_class in {"site_doc", "field_notes"}:
            score += 0.2
        elif source_class in {"training_corpus"}:
            score -= 1.0

    if "capsman" in q:
        if "routeros_wireless" in path_l or ("wireless" in path_l and source_class == "controller_doc"):
            score += 1.6
        elif source_class == "training_corpus":
            score -= 0.6
    if "vlan" in q and "capsman" in q:
        if source_class == "controller_doc":
            score += 0.5

    if query_class == "subscriber":
        if source_class in {"site_doc", "controller_doc", "reference", "field_notes"}:
            score += 0.5
        elif source_class in {"training_corpus"}:
            score -= 0.5

    if path_l.startswith("docs/jake/") and query_class in {"site", "controller"}:
        score -= 0.7
    if path_l.startswith("docs/training/") and query_class in {"site", "controller"}:
        score -= 0.5

    return score


def hard_match(doc, query):
    doc_l = doc.lower()
    q = query.lower()

    score = 0
    for t in ["br-cgnat", "dhcp", "rogue", "splynx", "000007"]:
        if t in q and t in doc_l:
            score += 1.5

    return score


def meta_gate(meta, query):
    path_l = str(meta.get("relative_path", "")).lower()
    source_class = str(meta.get("source_class") or "").lower()
    query_class = detect_query_class(query)
    site_id, aliases = infer_site_context(query)

    if query_class == "site" and site_id:
        site_hit = site_id in path_l or any(alias in path_l for alias in aliases)
        if source_class in {"jake_doc", "training_corpus"} and not site_hit:
            return -0.9
    if query_class == "controller":
        if source_class in {"controller_doc", "reference", "runbook"}:
            return 0.0
        if source_class in {"training_corpus"}:
            return -1.0
    if query_class == "procedure" and source_class == "training_corpus":
        return -0.5
    return 0.0


def rescore(results, query):
    out = []

    if not results["documents"] or not results["documents"][0]:
        return []

    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        boost = keyword_boost(doc, meta, query) + hard_match(doc, query) + meta_gate(meta, query)
        score = dist - boost
        out.append((score, doc, meta, dist, boost))

    out.sort(key=lambda x: x[0])
    return out


def fallback(collection, query):
    q_emb = embed_query(query)
    r = collection.query(
        query_embeddings=[q_emb],
        n_results=24,
        include=["documents", "metadatas", "distances"],
    )
    return rescore(r, query)


def search(query: str, n_results=12):
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    col = client.get_collection(COLLECTION_NAME)

    q_emb = embed_query(query)
    sysf = detect_system_filter(query)

    site_id, aliases = infer_site_context(query)
    args = dict(
        query_embeddings=[q_emb],
        n_results=max(n_results, 18),
        include=["documents", "metadatas", "distances"],
    )

    if sysf:
        args["where"] = {"system": sysf}

    r = col.query(**args)
    scored = rescore(r, query)

    if not scored or scored[0][0] > 0.75:
        scored = fallback(col, query)

    seen = set()
    out = []

    for item in scored:
        _, _, meta, _, _ = item
        key = meta.get("relative_path", "")

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    if site_id:
        exact = []
        rest = []
        for item in out:
            meta = item[2]
            path_l = str(meta.get("relative_path", "")).lower()
            if site_id in path_l or any(alias in path_l for alias in aliases):
                exact.append(item)
            else:
                rest.append(item)
        out = exact + rest

    return out[:6]


if __name__ == "__main__":
    q = input("Query: ").strip()
    results = search(q)

    for i, (s, doc, meta, dist, boost) in enumerate(results, 1):
        print(f"\n=== {i} dist={dist:.3f} boost={boost:.2f} score={s:.3f}")
        print(meta.get("relative_path"))
        print(doc[:800])
