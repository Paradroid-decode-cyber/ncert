"""
bkt_engine.py  —  Bayesian Knowledge Tracing + Ebbinghaus decay + ZPD

BKT Hidden Markov Model:
  States : L=0 (not learned), L=1 (learned)
  Params :
    p_init    — prior P(L=1) at first encounter          default 0.10
    p_transit — P(L=0→L=1) per correct answer           default 0.20
    p_slip    — P(wrong | L=1)                           default 0.10
    p_guess   — P(correct | L=0)                         default 0.20

Ebbinghaus forgetting:
    score_decayed = score × e^(−λ × days_since_seen)    λ=0.05

ZPD zones (post-decay):
    < 0.40  → easy    (scaffold from scratch)
    0.40–0.75 → medium  (normal explanation)
    > 0.75  → hard    (exam-level complexity)

Prerequisite graph:
    DAG of concept dependencies.
    A topic is blocked if any prerequisite mastery < PREREQ_THRESHOLD (0.50).
"""
from __future__ import annotations

import math
import time
import sqlite3
import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("bkt_engine")

# ── BKT defaults ─────────────────────────────────────────────────────────────
P_INIT      = 0.10
P_TRANSIT   = 0.20
P_SLIP      = 0.10
P_GUESS     = 0.20

# ── ZPD thresholds ────────────────────────────────────────────────────────────
ZPD_LOWER   = 0.40   # below → easy
ZPD_UPPER   = 0.75   # above → hard

# ── Forgetting curve ──────────────────────────────────────────────────────────
DECAY_LAMBDA   = 0.05          # λ — tune this (0.03=slow, 0.10=fast forgetting)
SECS_PER_DAY   = 86400

# ── Prerequisite gate ─────────────────────────────────────────────────────────
PREREQ_THRESHOLD = 0.50

# Topic prerequisite DAG  (topic → list of required topics)
PREREQUISITE_GRAPH: Dict[str, List[str]] = {
    # Optics
    "Total Internal Reflection": ["Refraction", "Snell's Law"],
    "Lens Formula":              ["Lens", "Refraction"],
    "Optical Instruments":       ["Lens Formula", "Reflection"],
    # Electricity
    "Kirchhoff's Laws":          ["Ohm's Law", "Electric Circuit"],
    "Wheatstone Bridge":         ["Kirchhoff's Laws", "Resistance"],
    "Electromagnetic Induction": ["Magnetic Effect", "Electric Circuit"],
    # Mechanics
    "Work Energy Power":         ["Force", "Motion"],
    "Conservation of Momentum":  ["Force", "Motion"],
    "Gravitation":               ["Force"],
    # Chemistry
    "Electrolysis":              ["Acid Base", "Electric Circuit"],
    "Electrochemistry":          ["Acid Base", "Redox Reactions"],
    "Polymers":                  ["Carbon Compounds"],
    # Biology
    "Genetics":                  ["Heredity", "Cell"],
    "Evolution":                 ["Genetics"],
    "Ecosystem":                 ["Photosynthesis", "Respiration"],
    # Maths
    "Quadratic Formula":         ["Quadratic"],
    "Trigonometric Identities":  ["Trigonometry"],
    "Coordinate Geometry":       ["Trigonometry"],
    "Probability":               ["Statistics"],
    "Calculus":                  ["Trigonometry", "Quadratic"],
}


# ══════════════════════════════════════════════════════════════════════════════
# BKT update functions
# ══════════════════════════════════════════════════════════════════════════════
def bkt_update(
    p_known:    float,
    is_correct: bool,
    p_transit:  float = P_TRANSIT,
    p_slip:     float = P_SLIP,
    p_guess:    float = P_GUESS,
) -> float:
    """
    One BKT step: update P(known) after observing a correct/wrong answer.

    P(known | correct) = P(correct | known) × P(known)
                         ─────────────────────────────
                              P(correct)
    """
    p_correct_given_known    = 1.0 - p_slip
    p_correct_given_unknown  = p_guess
    p_wrong_given_known      = p_slip
    p_wrong_given_unknown    = 1.0 - p_guess

    if is_correct:
        numerator   = p_correct_given_known   * p_known
        denominator = (p_correct_given_known  * p_known
                     + p_correct_given_unknown * (1 - p_known))
    else:
        numerator   = p_wrong_given_known     * p_known
        denominator = (p_wrong_given_known    * p_known
                     + p_wrong_given_unknown  * (1 - p_known))

    if denominator < 1e-9:
        return p_known

    p_known_posterior = numerator / denominator

    # Apply learning transition: even after a wrong answer, can still learn
    p_known_next = p_known_posterior + (1 - p_known_posterior) * p_transit
    return min(1.0, max(0.0, p_known_next))


def apply_forgetting_decay(score: float, last_seen_ts: float) -> float:
    """
    Apply Ebbinghaus exponential forgetting curve.
    score_decayed = score × e^(−λ × days_elapsed)
    """
    if last_seen_ts <= 0:
        return score
    days = (time.time() - last_seen_ts) / SECS_PER_DAY
    return score * math.exp(-DECAY_LAMBDA * days)


def zpd_zone(score: float) -> str:
    """Map mastery score to ZPD zone string."""
    if score < ZPD_LOWER:  return "easy"
    if score < ZPD_UPPER:  return "medium"
    return "hard"


# ══════════════════════════════════════════════════════════════════════════════
# BKTEngine — wraps SQLite reads/writes
# ══════════════════════════════════════════════════════════════════════════════
class BKTEngine:
    """
    Stateless engine — all state lives in SQLite concept_mastery table.
    Create once, call per-request.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS concept_mastery (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       TEXT NOT NULL,
        topic         TEXT NOT NULL,
        mastery_score REAL DEFAULT 0.10,
        p_transit     REAL DEFAULT 0.20,
        p_slip        REAL DEFAULT 0.10,
        p_guess       REAL DEFAULT 0.20,
        visit_count   INTEGER DEFAULT 0,
        correct_count INTEGER DEFAULT 0,
        wrong_count   INTEGER DEFAULT 0,
        last_seen_ts  REAL DEFAULT 0,
        created_at    REAL DEFAULT (unixepoch()),
        UNIQUE(user_id, topic)
    );
    CREATE INDEX IF NOT EXISTS idx_mastery_user ON concept_mastery(user_id);
    """

    def __init__(self, db_path: str):
        self.db = db_path
        with sqlite3.connect(db_path) as c:
            c.executescript(self.SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    # ── Read ──────────────────────────────────────────────────────
    def get_mastery(self, user_id: str, topic: str) -> float:
        """
        Return current mastery score with Ebbinghaus decay applied.
        Returns P_INIT (0.10) if topic never seen.
        """
        with self._conn() as c:
            row = c.execute(
                "SELECT mastery_score, last_seen_ts FROM concept_mastery WHERE user_id=? AND topic=?",
                (user_id, topic)
            ).fetchone()
        if not row:
            return P_INIT
        return apply_forgetting_decay(row["mastery_score"], row["last_seen_ts"])

    def get_all_mastery(self, user_id: str) -> Dict[str, float]:
        """Return {topic: decayed_score} for all topics the user has encountered."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT topic, mastery_score, last_seen_ts FROM concept_mastery WHERE user_id=?",
                (user_id,)
            ).fetchall()
        return {
            r["topic"]: apply_forgetting_decay(r["mastery_score"], r["last_seen_ts"])
            for r in rows
        }

    def get_avg_mastery(self, user_id: str, topics: Optional[List[str]] = None) -> float:
        """Average mastery across topics (optionally filtered)."""
        all_m = self.get_all_mastery(user_id)
        if topics:
            scores = [all_m.get(t, P_INIT) for t in topics]
        else:
            scores = list(all_m.values())
        return sum(scores) / len(scores) if scores else P_INIT

    # ── Update ────────────────────────────────────────────────────
    def record_answer(
        self,
        user_id:    str,
        topic:      str,
        is_correct: bool,
    ) -> float:
        """
        Update BKT state after a quiz answer.
        Returns new mastery score.
        """
        with self._conn() as c:
            row = c.execute(
                "SELECT mastery_score, p_transit, p_slip, p_guess, visit_count, correct_count, wrong_count "
                "FROM concept_mastery WHERE user_id=? AND topic=?",
                (user_id, topic)
            ).fetchone()

            if row:
                current = apply_forgetting_decay(row["mastery_score"], 0)  # decay already applied above
                p_t = row["p_transit"]; p_s = row["p_slip"]; p_g = row["p_guess"]
                visits  = row["visit_count"]
                corrects= row["correct_count"]
                wrongs  = row["wrong_count"]
            else:
                current = P_INIT
                p_t, p_s, p_g = P_TRANSIT, P_SLIP, P_GUESS
                visits = corrects = wrongs = 0

            new_score = bkt_update(current, is_correct, p_t, p_s, p_g)
            now       = time.time()

            c.execute("""
                INSERT INTO concept_mastery
                    (user_id, topic, mastery_score, p_transit, p_slip, p_guess,
                     visit_count, correct_count, wrong_count, last_seen_ts)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id, topic) DO UPDATE SET
                    mastery_score = excluded.mastery_score,
                    visit_count   = excluded.visit_count,
                    correct_count = excluded.correct_count,
                    wrong_count   = excluded.wrong_count,
                    last_seen_ts  = excluded.last_seen_ts
            """, (
                user_id, topic, new_score, p_t, p_s, p_g,
                visits+1,
                corrects + (1 if is_correct else 0),
                wrongs   + (0 if is_correct else 1),
                now,
            ))

        log.debug(f"BKT {user_id[:8]} {topic}: {current:.2f}→{new_score:.2f} ({'✓' if is_correct else '✗'})")
        return new_score

    def mark_visited(self, user_id: str, topic: str):
        """
        Record that the user viewed content on this topic (no quiz).
        Updates last_seen_ts so decay resets; does not change mastery score.
        """
        with self._conn() as c:
            c.execute("""
                INSERT INTO concept_mastery (user_id, topic, last_seen_ts, visit_count)
                VALUES (?,?,?,1)
                ON CONFLICT(user_id, topic) DO UPDATE SET
                    last_seen_ts = ?,
                    visit_count  = visit_count + 1
            """, (user_id, topic, time.time(), time.time()))

    # ── ZPD + prereqs ─────────────────────────────────────────────
    def get_zpd(self, user_id: str, topic: str) -> Tuple[str, float]:
        """
        Returns (zone, decayed_score) for a topic.
        zone = "easy" | "medium" | "hard"
        """
        score = self.get_mastery(user_id, topic)
        return zpd_zone(score), score

    def check_prerequisites(
        self,
        user_id: str,
        topic:   str,
    ) -> Tuple[bool, List[str]]:
        """
        Check if all prerequisites for topic are mastered.

        Returns:
            (can_proceed, missing_prereqs)
            can_proceed    — True if all prereqs mastered or no prereqs
            missing_prereqs — list of topics with mastery < PREREQ_THRESHOLD
        """
        prereqs = PREREQUISITE_GRAPH.get(topic, [])
        if not prereqs:
            return True, []

        missing = []
        all_mastery = self.get_all_mastery(user_id)
        for prereq in prereqs:
            score = all_mastery.get(prereq, P_INIT)
            if score < PREREQ_THRESHOLD:
                missing.append(prereq)

        return (len(missing) == 0), missing

    # ── Adaptive params ───────────────────────────────────────────
    def adapt_params(
        self,
        user_id:  str,
        topic:    str,
        n_recent: int = 5,
    ) -> Dict[str, float]:
        """
        Estimate per-student BKT params from recent answer history.
        Returns {p_transit, p_slip, p_guess} — falls back to defaults if not enough data.
        """
        with self._conn() as c:
            row = c.execute(
                "SELECT correct_count, wrong_count, visit_count FROM concept_mastery "
                "WHERE user_id=? AND topic=?",
                (user_id, topic)
            ).fetchone()

        if not row or row["visit_count"] < 5:
            return {"p_transit": P_TRANSIT, "p_slip": P_SLIP, "p_guess": P_GUESS}

        total    = row["correct_count"] + row["wrong_count"]
        acc      = row["correct_count"] / total if total else 0.5

        # Heuristic adaptive params based on accuracy
        p_slip    = max(0.05, min(0.25, (1 - acc) * 0.3))
        p_guess   = max(0.10, min(0.40, (1 - acc) * 0.5))
        p_transit = max(0.10, min(0.40, acc * 0.4))

        return {"p_transit": p_transit, "p_slip": p_slip, "p_guess": p_guess}
