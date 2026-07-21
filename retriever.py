"""
retriever.py  —  Semantic RAG retrieval from SQLite using numpy cosine similarity

No Pinecone. Embeddings are loaded from SQLite into numpy at query time.

Performance:
  Grade 10 Physics (1 chapter ~40 chunks) → ~8ms
  Full Grade 10 DB (~400 chunks)           → ~30ms
  Full DB all grades (~2000 chunks)        → ~80ms

Usage:
    retriever = NCERTRetriever(db_path)
    result    = retriever.search("how does refraction work", grade=10, subject="Physics")
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

log = logging.getLogger("retriever")

EMBED_MODEL     = "all-MiniLM-L6-v2"
TOP_K_CHUNKS    = 5
TOP_K_IMAGES    = 2
IMAGE_THRESHOLD = 0.35
RAG_THRESHOLD   = 0.45   # below this → web_fallback


# ── Singleton embedder ────────────────────────────────────────────────────────
_embedder: Optional[SentenceTransformer] = None

def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        log.info(f"Loading embedder: {EMBED_MODEL}")
        _embedder = SentenceTransformer(EMBED_MODEL)
    return _embedder


# ══════════════════════════════════════════════════════════════════════════════
# Result dataclass
# ══════════════════════════════════════════════════════════════════════════════
class RAGResult:
    def __init__(self):
        self.found      = False
        self.score      = 0.0       # best cosine similarity
        self.context    = ""        # concatenated chunk text
        self.chunks     = []        # raw chunk dicts
        self.source     = "none"    # "rag" | "none"
        self.source_refs= []        # citation list
        self.images     = []        # matching image dicts (caption + file_path)


# ══════════════════════════════════════════════════════════════════════════════
# NCERTRetriever
# ══════════════════════════════════════════════════════════════════════════════
class NCERTRetriever:

    def __init__(self, db_path: str):
        self.db = db_path

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    # ── Public API ────────────────────────────────────────────────

    def search(
        self,
        query:   str,
        grade:   int,
        subject: Optional[str] = None,
        top_k:   int           = TOP_K_CHUNKS,
    ) -> RAGResult:
        """
        Search for relevant NCERT text chunks for the given query.

        Steps:
          1. Embed query with MiniLM-L6-v2
          2. Load chunk embeddings for (grade, [subject]) from SQLite
          3. Vectorised cosine similarity (numpy)
          4. Return top_k chunks above threshold + top-2 matching images
        """
        result = RAGResult()
        query_vec = get_embedder().encode(query, convert_to_numpy=True)

        # ── Load chunks ───────────────────────────────────────────
        chunks = self._load_chunks(grade, subject)
        if not chunks:
            log.warning(f"No chunks found for grade={grade} subject={subject}")
            return result

        # ── Cosine similarity ─────────────────────────────────────
        matrix  = np.array([c["_vec"] for c in chunks], dtype=np.float32)
        q_norm  = query_vec / (np.linalg.norm(query_vec) + 1e-9)
        m_norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
        sims    = (matrix / m_norms) @ q_norm

        top_idxs = np.argsort(sims)[::-1][:top_k]
        best_sim = float(sims[top_idxs[0]])

        if best_sim < RAG_THRESHOLD:
            log.info(f"RAG score {best_sim:.3f} below threshold — web fallback needed")
            return result

        result.found  = True
        result.score  = best_sim
        result.source = "rag"

        top_chunks = []
        for idx in top_idxs:
            if sims[idx] < 0.20:   # skip very low scores
                continue
            c = chunks[idx]
            top_chunks.append({
                "chunk_id":  c["chunk_id"],
                "text":      c["text"],
                "score":     float(sims[idx]),
                "page_start":c["page_start"],
                "page_end":  c["page_end"],
                "chapter":   c["chapter"],
                "subject":   c["subject"],
                "concepts":  json.loads(c["concepts"] or "[]"),
            })

        result.chunks = top_chunks
        result.context = "\n\n".join(c["text"] for c in top_chunks)
        result.source_refs = list({
            f"NCERT Class {grade} {c['subject']} — {c['chapter']} p.{c['page_start']}"
            for c in top_chunks
        })

        # ── Image retrieval ───────────────────────────────────────
        result.images = self._search_images(query_vec, grade, subject)

        return result

    def search_images(
        self,
        query:   str,
        grade:   int,
        subject: Optional[str] = None,
        top_k:   int = TOP_K_IMAGES,
    ) -> List[Dict]:
        """Standalone image search (caption embedding similarity)."""
        query_vec = get_embedder().encode(query, convert_to_numpy=True)
        return self._search_images(query_vec, grade, subject, top_k)

    # ── Private ───────────────────────────────────────────────────

    def _load_chunks(
        self,
        grade:   int,
        subject: Optional[str],
    ) -> List[Dict]:
        """Load chunks with embeddings from SQLite, filtered by grade/subject."""
        with self._conn() as c:
            # Get columns of ncert_chunks table
            cursor = c.execute('PRAGMA table_info(ncert_chunks)')
            available_columns = {col[1] for col in cursor.fetchall()}

            desired_columns = ['chunk_id', 'text', 'page_start', 'page_end', 'chapter', 'subject', 'concepts', 'embedding', 'grade']
            
            # Select only the columns that exist in the table
            select_columns = [col for col in desired_columns if col in available_columns]
            
            # 'embedding' and 'text' are essential
            if 'embedding' not in select_columns or 'text' not in select_columns:
                log.error("The 'embedding' and/or 'text' column is missing from the 'ncert_chunks' table.")
                return []

            select_clause = ", ".join(select_columns)

            where_clauses = []
            params = []

            if 'grade' in available_columns:
                where_clauses.append("grade=?")
                params.append(grade)
            
            if subject and 'subject' in available_columns:
                where_clauses.append("subject=?")
                params.append(subject)

            where_clause = " AND ".join(where_clauses)
            query = f"SELECT {select_clause} FROM ncert_chunks"
            if where_clause:
                query += f" WHERE {where_clause}"

            rows = c.execute(query, params).fetchall()

        chunks = []
        for r in rows:
            try:
                d = dict(r)
                vec = np.array(json.loads(d["embedding"]), dtype=np.float32)
                d["_vec"] = vec

                # Provide default values for missing columns
                if 'page_start' not in d: d['page_start'] = 'N/A'
                if 'page_end' not in d: d['page_end'] = 'N/A'
                if 'chapter' not in d: d['chapter'] = 'Unknown Chapter'
                if 'subject' not in d: d['subject'] = subject or 'Unknown Subject'
                if 'concepts' not in d: d['concepts'] = '[]'
                if 'chunk_id' not in d: d['chunk_id'] = 'Unknown'
                if 'text' not in d: d['text'] = ''
                if 'grade' not in d: d['grade'] = grade

                chunks.append(d)
            except (json.JSONDecodeError, KeyError) as e:
                log.warning(f"Skipping malformed row: {r}. Error: {e}")
                pass
        return chunks

    def _search_images(
        self,
        query_vec: np.ndarray,
        grade:     int,
        subject:   Optional[str],
        top_k:     int = TOP_K_IMAGES,
    ) -> List[Dict]:
        """
        Find relevant images by comparing caption embeddings to query vector.
        Same 384-dim space as text — no CLIP needed.
        """
        with self._conn() as c:
            if subject:
                rows = c.execute(
                    "SELECT image_id, file_path, caption, page, image_type, concepts, embedding "
                    "FROM ncert_images WHERE grade=? AND subject=?",
                    (grade, subject)
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT image_id, file_path, caption, page, image_type, concepts, embedding "
                    "FROM ncert_images WHERE grade=?",
                    (grade,)
                ).fetchall()

        if not rows:
            return []

        vecs   = []
        valid  = []
        for r in rows:
            try:
                vecs.append(np.array(json.loads(r["embedding"]), dtype=np.float32))
                valid.append(dict(r))
            except Exception:
                pass

        if not vecs:
            return []

        matrix  = np.array(vecs, dtype=np.float32)
        q_norm  = query_vec / (np.linalg.norm(query_vec) + 1e-9)
        m_norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
        sims    = (matrix / m_norms) @ q_norm

        top_idxs = np.argsort(sims)[::-1][:top_k]
        results  = []
        for idx in top_idxs:
            if sims[idx] < IMAGE_THRESHOLD:
                continue
            img = valid[idx].copy()
            img["score"]    = float(sims[idx])
            img["concepts"] = json.loads(img.get("concepts") or "[]")
            img.pop("embedding", None)
            results.append(img)

        return results

    # ── Stats ─────────────────────────────────────────────────────
    def stats(self) -> Dict:
        with self._conn() as c:
            n_chunks = c.execute("SELECT COUNT(*) FROM ncert_chunks").fetchone()[0]
            n_images = c.execute("SELECT COUNT(*) FROM ncert_images").fetchone()[0]
            grades   = [r[0] for r in c.execute(
                "SELECT DISTINCT grade FROM ncert_chunks ORDER BY grade").fetchall()]
        return {"chunks": n_chunks, "images": n_images, "grades": grades}
