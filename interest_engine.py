"""
interest_engine.py  —  Exam mode, frustration, boredom, interest scoring

Signals detected:
  exam_mode    — query contains exam/revision keywords; sticky for session
  frustrated   — consecutive_low_ratings >= 3
  bored        — mastery > 0.75 AND avg_dwell < 10s (knows it, moving fast)
  disengaged   — avg_scroll < 0.20 for last 5 responses
  high_interest— follow_up_count >= 2 on same topic

Interest score (0-1):
    0.4 × dwell_norm + 0.3 × revisit_rate + 0.3 × follow_up_rate
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Optional

log = logging.getLogger("interest_engine")

# ── Exam mode keywords ────────────────────────────────────────────────────────
_EXAM_KEYWORDS = [
    "exam","test","jee","neet","board","cbse","icse","revision","revise",
    "practice","mock","mcq","question paper","past paper","previous year",
    "important questions","short answer","long answer","marking scheme",
    "last minute","quick revision","formula sheet","cheat sheet",
]

# ── Thresholds ────────────────────────────────────────────────────────────────
FRUSTRATION_THRESHOLD   = 3    # consecutive low ratings
BOREDOM_MASTERY_MIN     = 0.75 # mastery above this
BOREDOM_DWELL_MAX_S     = 10.0 # avg dwell below this
DISENGAGE_SCROLL_MAX    = 0.20 # avg scroll below this


@dataclass
class InterestState:
    exam_mode:       bool  = False
    frustrated:      bool  = False
    bored:           bool  = False
    disengaged:      bool  = False
    high_interest:   bool  = False
    interest_score:  float = 0.5
    # raw signals for context builder
    exam_triggered_by: str = ""   # the keyword that triggered exam mode


def detect_exam_mode(query: str) -> tuple[bool, str]:
    """Return (is_exam_mode, triggering_keyword)."""
    q = query.lower()
    for kw in _EXAM_KEYWORDS:
        if kw in q:
            return True, kw
    return False, ""


def compute_interest_score(
    dwell_times_s:  List[float],
    follow_up_count: int,
    query_count:     int,
    session_revisits: int = 0,
) -> float:
    """
    Composite interest score [0, 1].

    Components:
      dwell_norm    — avg dwell normalised to [0,1] (cap at 120s)
      revisit_rate  — how often student returns to same topic in session
      follow_up_rate— follow_ups / total queries
    """
    avg_dwell = sum(dwell_times_s)/len(dwell_times_s) if dwell_times_s else 0
    dwell_norm    = min(1.0, avg_dwell / 120.0)
    revisit_rate  = min(1.0, session_revisits / max(1, query_count))
    follow_up_rate= min(1.0, follow_up_count  / max(1, query_count))

    return round(0.4*dwell_norm + 0.3*revisit_rate + 0.3*follow_up_rate, 3)


def evaluate_state(
    query:                  str,
    consecutive_low_ratings:int,
    current_mastery:        float,
    dwell_times_s:          List[float],
    scroll_depths:          List[float],
    follow_up_count:        int,
    query_count:            int,
    existing_exam_mode:     bool = False,
) -> InterestState:
    """
    Full interest state evaluation for one query turn.

    exam_mode is sticky — once True it stays True for the session.
    """
    state = InterestState()

    # ── exam mode ─────────────────────────────────────────────────
    if existing_exam_mode:
        state.exam_mode = True
    else:
        triggered, kw = detect_exam_mode(query)
        state.exam_mode         = triggered
        state.exam_triggered_by = kw

    # ── frustration ───────────────────────────────────────────────
    state.frustrated = consecutive_low_ratings >= FRUSTRATION_THRESHOLD

    # ── boredom ───────────────────────────────────────────────────
    avg_dwell = sum(dwell_times_s)/len(dwell_times_s) if dwell_times_s else 30.0
    state.bored = (
        current_mastery > BOREDOM_MASTERY_MIN
        and avg_dwell < BOREDOM_DWELL_MAX_S
        and query_count >= 3
    )

    # ── disengagement ─────────────────────────────────────────────
    recent_scroll = scroll_depths[-5:] if len(scroll_depths)>=5 else scroll_depths
    avg_scroll    = sum(recent_scroll)/len(recent_scroll) if recent_scroll else 0.5
    state.disengaged = avg_scroll < DISENGAGE_SCROLL_MAX and query_count >= 3

    # ── high interest ─────────────────────────────────────────────
    state.high_interest = follow_up_count >= 2

    # ── interest score ────────────────────────────────────────────
    state.interest_score = compute_interest_score(
        dwell_times_s, follow_up_count, query_count
    )

    return state
