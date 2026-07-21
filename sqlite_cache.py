"""
sqlite_cache.py  —  Session + Profile cache (replaces Redis)
WAL mode, 2h session TTL, 24h profile TTL.
"""
from __future__ import annotations
import json, time, sqlite3, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

log = logging.getLogger("sqlite_cache")
SESSION_TTL_S = 7200    # 2 h
PROFILE_TTL_S = 86400   # 24 h

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS session_cache (
    session_id              TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    started_at              REAL,
    last_query_at           REAL,
    expires_at              REAL,
    active_subject          TEXT DEFAULT '',
    active_chapter          TEXT DEFAULT '',
    recent_topics           TEXT DEFAULT '[]',
    recent_errors           TEXT DEFAULT '[]',
    query_gaps_s            TEXT DEFAULT '[]',
    dwell_times_s           TEXT DEFAULT '[]',
    scroll_depths           TEXT DEFAULT '[]',
    query_count             INTEGER DEFAULT 0,
    follow_up_count         INTEGER DEFAULT 0,
    voice_count             INTEGER DEFAULT 0,
    text_count              INTEGER DEFAULT 0,
    consecutive_low_ratings INTEGER DEFAULT 0,
    session_mastery_samples TEXT DEFAULT '[]',
    difficulty_adjustments  TEXT DEFAULT '[]',
    session_ratings         TEXT DEFAULT '[]',
    exam_mode               INTEGER DEFAULT 0,
    language_override       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS profile_cache (
    user_id    TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    cached_at  REAL,
    expires_at REAL
);

CREATE INDEX IF NOT EXISTS idx_sess_user   ON session_cache(user_id);
CREATE INDEX IF NOT EXISTS idx_sess_exp    ON session_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_prof_exp    ON profile_cache(expires_at);
"""

# ── helpers ───────────────────────────────────────────────────────────────────
def _roll(lst: list, v: Any, n: int):
    lst.append(v); lst[:] = lst[-n:]

# ── SessionData ───────────────────────────────────────────────────────────────
@dataclass
class SessionData:
    session_id:              str
    user_id:                 str
    started_at:              float = field(default_factory=time.time)
    last_query_at:           float = field(default_factory=time.time)
    expires_at:              float = field(default_factory=lambda: time.time()+SESSION_TTL_S)
    active_subject:          str         = ""
    active_chapter:          str         = ""
    recent_topics:           List[str]   = field(default_factory=list)
    recent_errors:           List[str]   = field(default_factory=list)
    query_gaps_s:            List[float] = field(default_factory=list)
    dwell_times_s:           List[float] = field(default_factory=list)
    scroll_depths:           List[float] = field(default_factory=list)
    query_count:             int  = 0
    follow_up_count:         int  = 0
    voice_count:             int  = 0
    text_count:              int  = 0
    consecutive_low_ratings: int  = 0
    session_mastery_samples: List = field(default_factory=list)
    difficulty_adjustments:  List = field(default_factory=list)
    session_ratings:         List = field(default_factory=list)
    exam_mode:               bool = False
    language_override:       str  = ""

    def is_expired(self) -> bool: return time.time() > self.expires_at
    def touch(self):
        now = time.time()
        if self.last_query_at:
            _roll(self.query_gaps_s, now - self.last_query_at, 20)
        self.last_query_at = now
        self.expires_at    = now + SESSION_TTL_S

    def append_dwell(self, s: float):  _roll(self.dwell_times_s, s, 20)
    def append_scroll(self, d: float): _roll(self.scroll_depths, max(0,min(1,d)), 20)
    def append_rating(self, r: int):
        self.session_ratings.append(r)
        self.consecutive_low_ratings = (self.consecutive_low_ratings+1) if r<=2 else 0
    def add_topic(self, t: str):
        if self.recent_topics and self.recent_topics[-1]==t: self.follow_up_count+=1
        _roll(self.recent_topics, t, 5)
    def add_error(self, e: str): _roll(self.recent_errors, e, 5)

    @property
    def avg_dwell(self):  return sum(self.dwell_times_s)/len(self.dwell_times_s) if self.dwell_times_s else 0
    @property
    def avg_scroll(self): return sum(self.scroll_depths)/len(self.scroll_depths)  if self.scroll_depths  else 0
    @property
    def avg_rating(self): return sum(self.session_ratings)/len(self.session_ratings) if self.session_ratings else 0


# ── SessionCache ──────────────────────────────────────────────────────────────
class SessionCache:
    def __init__(self, db_path: str):
        self.db = db_path
        with sqlite3.connect(db_path) as c: c.executescript(SCHEMA)

    def _conn(self):
        c = sqlite3.connect(self.db, timeout=10); c.row_factory=sqlite3.Row; return c

    def get_or_create(self, user_id: str, session_id: str) -> SessionData:
        s = self._load(session_id)
        if s and not s.is_expired(): return s
        s = SessionData(session_id=session_id, user_id=user_id)
        self._save(s); return s

    def get(self, session_id: str) -> Optional[SessionData]:
        s = self._load(session_id)
        return s if (s and not s.is_expired()) else None

    def update(self, s: SessionData): self._save(s)

    def delete(self, session_id: str):
        with self._conn() as c: c.execute("DELETE FROM session_cache WHERE session_id=?",(session_id,))

    def purge_expired(self):
        with self._conn() as c:
            n = c.execute("DELETE FROM session_cache WHERE expires_at<?", (time.time(),)).rowcount
        if n: log.info(f"Purged {n} expired sessions")

    def active_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM session_cache WHERE expires_at>?",(time.time(),)).fetchone()[0]

    def _load(self, sid: str) -> Optional[SessionData]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM session_cache WHERE session_id=?",(sid,)).fetchone()
        return self._row(dict(row)) if row else None

    def _save(self, s: SessionData):
        with self._conn() as c:
            c.execute("""INSERT OR REPLACE INTO session_cache VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                s.session_id, s.user_id, s.started_at, s.last_query_at, s.expires_at,
                s.active_subject, s.active_chapter,
                json.dumps(s.recent_topics), json.dumps(s.recent_errors),
                json.dumps(s.query_gaps_s),  json.dumps(s.dwell_times_s),
                json.dumps(s.scroll_depths),
                s.query_count, s.follow_up_count, s.voice_count, s.text_count,
                s.consecutive_low_ratings,
                json.dumps(s.session_mastery_samples),
                json.dumps(s.difficulty_adjustments),
                json.dumps(s.session_ratings),
                int(s.exam_mode), s.language_override,
            ))

    @staticmethod
    def _row(r: dict) -> SessionData:
        jl = lambda k: json.loads(r.get(k) or "[]")
        return SessionData(
            session_id=r["session_id"], user_id=r["user_id"],
            started_at=r["started_at"], last_query_at=r["last_query_at"],
            expires_at=r["expires_at"], active_subject=r.get("active_subject",""),
            active_chapter=r.get("active_chapter",""),
            recent_topics=jl("recent_topics"),   recent_errors=jl("recent_errors"),
            query_gaps_s=jl("query_gaps_s"),      dwell_times_s=jl("dwell_times_s"),
            scroll_depths=jl("scroll_depths"),
            query_count=r.get("query_count",0),   follow_up_count=r.get("follow_up_count",0),
            voice_count=r.get("voice_count",0),   text_count=r.get("text_count",0),
            consecutive_low_ratings=r.get("consecutive_low_ratings",0),
            session_mastery_samples=jl("session_mastery_samples"),
            difficulty_adjustments=jl("difficulty_adjustments"),
            session_ratings=jl("session_ratings"),
            exam_mode=bool(r.get("exam_mode",0)),
            language_override=r.get("language_override",""),
        )


# ── ProfileCache ──────────────────────────────────────────────────────────────
class ProfileCache:
    def __init__(self, db_path: str):
        self.db = db_path
        with sqlite3.connect(db_path) as c: c.executescript(SCHEMA)

    def _conn(self):
        c = sqlite3.connect(self.db, timeout=10); c.row_factory=sqlite3.Row; return c

    def get(self, user_id: str) -> Optional[Dict]:
        with self._conn() as c:
            row = c.execute("SELECT data,expires_at FROM profile_cache WHERE user_id=?",(user_id,)).fetchone()
        if not row: return None
        if time.time() > row["expires_at"]: self.invalidate(user_id); return None
        return json.loads(row["data"])

    def set(self, user_id: str, profile: Dict):
        now=time.time()
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO profile_cache VALUES(?,?,?,?)",
                      (user_id, json.dumps(profile,default=str), now, now+PROFILE_TTL_S))

    def invalidate(self, user_id: str):
        with self._conn() as c:
            c.execute("DELETE FROM profile_cache WHERE user_id=?",(user_id,))

    def purge_expired(self):
        with self._conn() as c: c.execute("DELETE FROM profile_cache WHERE expires_at<?", (time.time(),))
