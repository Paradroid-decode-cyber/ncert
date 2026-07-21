"""
main.py  —  FastAPI application

Routes:
  GET  /profile               — get own profile
  PUT  /profile               — update profile (grade, language, exams…)
  POST /chat                  — send query, get personalized response
  POST /chat/feedback         — submit dwell/scroll/rating after reading
  POST /quiz/submit           — submit quiz answer → BKT update
  GET  /quiz/generate         — generate quiz question for a topic
  GET  /mastery               — get mastery scores for all topics
  GET  /health                — service health + LLM info

Run:  
  uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import os, json, time, uuid, sqlite3, hashlib, logging
from typing import Dict, List, Optional

from fastapi                    import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors    import CORSMiddleware

from pydantic                   import BaseModel, Field
from dotenv                     import load_dotenv


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("main")

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH    = os.getenv("DATABASE_URL", "./db/ncert_tutor.db")


# ── Lazy pipeline import (avoids loading models at import time) ───────────────
_pipeline_loaded = False

def _get_pipeline():
    global _pipeline_loaded
    if not _pipeline_loaded:
        from graph.pipeline import run_pipeline as _rp, get_graph
        get_graph()   # compile graph + warm embedder
        _pipeline_loaded = True
    from graph.pipeline import run_pipeline
    return run_pipeline

def _get_bkt():
    from bkt_engine import BKTEngine
    return BKTEngine(DB_PATH)

# ══════════════════════════════════════════════════════════════════════════════
# DB init
# ══════════════════════════════════════════════════════════════════════════════
def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS users (
            user_id      TEXT PRIMARY KEY,
            email        TEXT UNIQUE NOT NULL,
            name         TEXT,
            password_hash TEXT NOT NULL,
            created_at   REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id              TEXT PRIMARY KEY,
            grade                INTEGER DEFAULT 10,
            board                TEXT    DEFAULT 'CBSE',
            preferred_language   TEXT    DEFAULT 'en',
            target_exams         TEXT    DEFAULT '[]',
            top_subjects         TEXT    DEFAULT '[]',
            style_vector         TEXT    DEFAULT '[0.5,0.5,0.5,0.5,0.5,0.5,0.5]',
            total_queries        INTEGER DEFAULT 0,
            school_type          TEXT    DEFAULT '',
            city_tier            INTEGER DEFAULT 2,
            last_active          REAL    DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS interactions (
            interaction_id TEXT PRIMARY KEY,
            user_id        TEXT,
            session_id     TEXT,
            query          TEXT,
            response       TEXT,
            source         TEXT,
            confidence     REAL,
            pctx_snapshot  TEXT,
            guardrail_report TEXT,
            created_at     REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS quiz_results (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT,
            topic          TEXT,
            question       TEXT,
            is_correct     INTEGER,
            difficulty     TEXT,
            mastery_before REAL,
            mastery_after  REAL,
            created_at     REAL DEFAULT (unixepoch())
        );
        """)
    log.info(f"DB ready: {DB_PATH}")


class ProfileUpdate(BaseModel):
    grade:              Optional[int]       = None
    board:              Optional[str]       = None
    preferred_language: Optional[str]       = None
    target_exams:       Optional[List[str]] = None
    top_subjects:       Optional[List[str]] = None
    school_type:        Optional[str]       = None

class ProfileCreate(BaseModel):
    name:     str
    email:    str
    password: str

class ChatRequest(BaseModel):
    query:      str
    topic:      str
    subject:    str
    session_id: Optional[str] = None
    input_type: str = "text"

class FeedbackRequest(BaseModel):
    interaction_id: str
    dwell_s:        float = 0.0
    scroll_depth:   float = 0.5
    rating:         Optional[int] = Field(None, ge=1, le=5)

class QuizSubmitRequest(BaseModel):
    topic:      str
    question:   str
    is_correct: bool
    difficulty: str = "medium"

class QuizGenerateRequest(BaseModel):
    topic:   str
    subject: str


# ══════════════════════════════════════════════════════════════════════════════
# App
# ══════════════════════════════════════════════════════════════════════════════
app = FastAPI(title="NCERT AI Tutor", version="3.0")

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_db()
    # Warm up pipeline in background
    import asyncio, concurrent.futures
    loop = asyncio.get_event_loop()
    loop.run_in_executor(concurrent.futures.ThreadPoolExecutor(), _get_pipeline)



# ── Profile ───────────────────────────────────────────────────────────────────
@app.get("/profile")
def get_profile(user_id: str):
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        row = c.execute(
            "SELECT u.name,u.email,p.* FROM users u JOIN user_profiles p USING(user_id) WHERE u.user_id=?",
            (user_id,)
        ).fetchone()
    if not row: raise HTTPException(404, "Profile not found")
    d = dict(row)
    d["style_vector"] = json.loads(d.get("style_vector") or "[]")
    d["target_exams"] = json.loads(d.get("target_exams") or "[]")
    d["top_subjects"] = json.loads(d.get("top_subjects") or "[]")
    return d


@app.put("/profile")
def update_profile(req: ProfileUpdate, user_id: str):
    fields, vals = [], []
    if req.grade              is not None: fields.append("grade=?");            vals.append(req.grade)
    if req.board              is not None: fields.append("board=?");            vals.append(req.board)
    if req.preferred_language is not None: fields.append("preferred_language=?"); vals.append(req.preferred_language)
    if req.target_exams       is not None: fields.append("target_exams=?");     vals.append(json.dumps(req.target_exams))
    if req.top_subjects       is not None: fields.append("top_subjects=?");     vals.append(json.dumps(req.top_subjects))
    if req.school_type        is not None: fields.append("school_type=?");      vals.append(req.school_type)
    if not fields: return {"status": "no changes"}
    vals.append(user_id)
    with sqlite3.connect(DB_PATH) as c:
        c.execute(f"UPDATE user_profiles SET {', '.join(fields)} WHERE user_id=?", vals)
    # Invalidate profile cache
    from sqlite_cache import ProfileCache
    ProfileCache(DB_PATH).invalidate(user_id)
    return {"status": "updated"}


@app.post("/profile")
def create_profile(req: ProfileCreate):
    user_id = str(uuid.uuid4())
    password_hash = hashlib.sha256(req.password.encode()).hexdigest()

    with sqlite3.connect(DB_PATH) as c:
        try:
            c.execute(
                "INSERT INTO users (user_id, email, name, password_hash) VALUES (?, ?, ?, ?)",
                (user_id, req.email, req.name, password_hash)
            )
            c.execute("INSERT INTO user_profiles (user_id) VALUES (?)", (user_id,))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f"User with email {req.email} already exists.")

    # Auditing
    if not os.path.exists("data"):
        os.makedirs("data")
    
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
        profile_data = dict(row)
        # Convert list-like strings to actual lists for JSON
        profile_data["target_exams"] = json.loads(profile_data.get("target_exams") or "[]")
        profile_data["top_subjects"] = json.loads(profile_data.get("top_subjects") or "[]")
        profile_data["style_vector"] = json.loads(profile_data.get("style_vector") or "[]")

    with open(f"data/{user_id}.json", "w") as f:
        json.dump(profile_data, f, indent=4)

    return {"user_id": user_id, "status": "created"}


# ── Chat ──────────────────────────────────────────────────────────────────────
@app.post("/chat")
def chat(req: ChatRequest, user_id: str):
    session_id = req.session_id or str(uuid.uuid4())

    # Get grade from profile
    with sqlite3.connect(DB_PATH) as c:
        row = c.execute("SELECT grade FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
    grade = row[0] if row else 10

    result = _get_pipeline()(
        user_id    = user_id,
        session_id = session_id,
        query      = req.query,
        topic      = req.topic,
        subject    = req.subject,
        grade      = grade,
        input_type = req.input_type,
    )

    if result.get("error"):
        raise HTTPException(500, result["error"])

    return {
        "response":       result["response"],
        "interaction_id": result["interaction_id"],
        "source":         result["source"],
        "confidence":     result["confidence"],
        "difficulty":     result["difficulty"],
        "mastery_pct":    result["mastery_pct"],
        "images":         result.get("images", []),
        "guardrails":     result.get("guardrails_triggered", []),
        "session_id":     session_id,
        "latency_ms":     result["latency_ms"],
    }


@app.post("/chat/feedback")
def chat_feedback(req: FeedbackRequest, user_id: str):
    """
    Submit behavioral feedback after student reads a response.
    dwell_s + scroll_depth + rating are used in next query's style signal detection.
    This endpoint stores them against the interaction for the next pipeline call.
    """
    with sqlite3.connect(DB_PATH) as c:
        c.execute(
            "UPDATE interactions SET pctx_snapshot=json_set(pctx_snapshot, '$.feedback_dwell', ?, "
            "'$.feedback_scroll', ?, '$.feedback_rating', ?) WHERE interaction_id=? AND user_id=?",
            (req.dwell_s, req.scroll_depth, req.rating, req.interaction_id, user_id)
        )
    return {"status": "ok"}


# ── Quiz ──────────────────────────────────────────────────────────────────────
@app.post("/quiz/submit")
def quiz_submit(req: QuizSubmitRequest, user_id: str):
    """Submit a quiz answer — updates BKT mastery for the topic."""
    bkt = _get_bkt()

    mastery_before = bkt.get_mastery(user_id, req.topic)
    mastery_after  = bkt.record_answer(user_id, req.topic, req.is_correct)

    # Log wrong answers to session recent_errors
    if not req.is_correct:
        from sqlite_cache import SessionCache
        # We don't have session_id here, so we write directly to a recent session
        # In production you'd pass session_id in the request
        pass

    with sqlite3.connect(DB_PATH) as c:
        c.execute(
            "INSERT INTO quiz_results (user_id,topic,question,is_correct,difficulty,mastery_before,mastery_after) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, req.topic, req.question, int(req.is_correct),
             req.difficulty, mastery_before, mastery_after)
        )

    return {
        "mastery_before": round(mastery_before, 3),
        "mastery_after":  round(mastery_after,  3),
        "zpd":            "easy" if mastery_after < 0.40 else ("medium" if mastery_after < 0.75 else "hard"),
        "correct":        req.is_correct,
    }


@app.get("/quiz/generate")
def quiz_generate(topic: str, subject: str, user_id: str):
    """Generate a quiz question for a topic using LLM."""
    from llm.llm_config import get_llm_response
    bkt     = _get_bkt()
    mastery = bkt.get_mastery(user_id, topic)
    diff    = "easy" if mastery < 0.40 else ("medium" if mastery < 0.75 else "hard")

    prompt = (
        f"Generate 1 {diff}-difficulty multiple-choice question about '{topic}' "
        f"for an NCERT {subject} student.\n"
        f"Return ONLY valid JSON:\n"
        f'{{"question":"...","options":["A)...","B)...","C)...","D)..."],"answer":"A","explanation":"..."}}'
    )
    try:
        raw  = get_llm_response(prompt, max_tokens=300, temperature=0.3)
        s    = raw.find("{"); e = raw.rfind("}")+1
        data = json.loads(raw[s:e])
        data["topic"]      = topic
        data["difficulty"] = diff
        data["mastery_pct"]= int(mastery*100)
        return data
    except Exception as ex:
        raise HTTPException(500, f"Quiz generation failed: {ex}")


# ── Mastery ───────────────────────────────────────────────────────────────────
@app.get("/mastery")
def get_mastery(user_id: str):
    """Return mastery scores for all topics (with decay applied)."""
    bkt = _get_bkt()
    all_m = bkt.get_all_mastery(user_id)
    return {
        "mastery": {
            topic: {
                "score":    round(score, 3),
                "pct":      int(score*100),
                "zone":     "easy" if score<0.40 else ("medium" if score<0.75 else "hard"),
            }
            for topic, score in sorted(all_m.items(), key=lambda x: -x[1])
        },
        "avg": round(sum(all_m.values())/len(all_m), 3) if all_m else 0,
        "total_topics": len(all_m),
    }


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    from llm.llm_config import llm_info
    from rag.retriever  import NCERTRetriever
    db_stats = NCERTRetriever(DB_PATH).stats()
    return {
        "status": "ok",
        "llm":    llm_info(),
        "db":     db_stats,
        "time":   time.time(),
    }



