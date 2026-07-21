"""
style_engine.py  —  7-dimensional EMA style vector

Dimensions (all 0.0–1.0):
  0  visual        — prefers diagrams described in text
  1  analogy       — prefers real-world analogies
  2  example       — prefers worked examples
  3  step_by_step  — prefers numbered steps
  4  formula_first — prefers formula shown before explanation
  5  depth         — prefers detailed (1.0) vs brief (0.0)
#   6  memory_tip    — prefers mnemonics / memory aidso;'[]

EMA update rule:  new[i] = α × signal[i] + (1−α) × current[i]   α=0.2
 
Signals are detected from:
  • Query text   — keyword matching → query_signals()
  • Feedback     — dwell time, scroll depth, rating → feedback_signals()

After ~20 consistent interactions the vector converges to reflect
the student's true preference for each dimension.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

log = logging.getLogger("style_engine")

EMA_ALPHA   = 0.20
N_DIMS      = 7
NEUTRAL_VEC = [0.5] * N_DIMS

# Dimension indices
DIM = dict(
    visual       = 0,
    analogy      = 1,
    example      = 2,
    step_by_step = 3,
    formula_first= 4,
    depth        = 5,
    memory_tip   = 6,
)

# Keyword → dimension triggers
_TRIGGERS: Dict[int, List[str]] = {
    DIM["visual"]:        ["diagram","draw","show","picture","figure","visualise","visual","chart","graph","sketch"],
    DIM["analogy"]:       ["like what","real life","analogy","imagine","compare","relate","daily life","example from life","just like"],
    DIM["example"]:       ["example","for instance","e.g.","such as","like","illustrate","demonstrate","show me how"],
    DIM["step_by_step"]:  ["step","steps","step by step","how to","procedure","process","guide","walkthrough","one by one","sequentially"],
    DIM["formula_first"]: ["formula","equation","derive","expression","mathematical","f=","v=","e=","a=","p=","law of","theorem"],
    DIM["depth"]:         ["explain","detail","elaborate","in depth","thoroughly","fully","complete","comprehensive","everything about"],
    DIM["memory_tip"]:    ["remember","memorize","trick","mnemonic","shortcut","easy way","how to remember","tip","hack","recall"],
}

# Negative triggers that lower a dimension
_NEG_TRIGGERS: Dict[int, List[str]] = {
    DIM["depth"]:         ["brief","short","quick","tldr","summary","in short","just tell me","simple","simple explanation","basics only"],
    DIM["formula_first"]: ["no formula","without formula","conceptually","intuitively","don't use math","explain without"],
    DIM["step_by_step"]:  ["in brief","just explain","overview","just tell me","direct answer"],
}


# ── Signal detection ──────────────────────────────────────────────────────────
def query_signals(query: str) -> List[float]:
    """
    Detect style signals from query text.
    Returns 7-dim float list [0,1]; 0.5 = no signal (neutral).
    """
    signals = [0.5] * N_DIMS
    q = query.lower()

    for dim, keywords in _TRIGGERS.items():
        if any(kw in q for kw in keywords):
            signals[dim] = 0.85

    for dim, keywords in _NEG_TRIGGERS.items():
        if any(kw in q for kw in keywords):
            signals[dim] = 0.15

    return signals


def feedback_signals(
    dwell_s:      float,
    scroll_depth: float,
    rating:       Optional[int],
    response_len: int = 0,
) -> List[float]:
    """
    Infer style preference from behavioural feedback signals.
    Returns 7-dim signal list.

    Heuristics:
      High dwell + high scroll   → depth ↑ (student wanted detail)
      Low  dwell + low  scroll   → depth ↓ (student wanted brevity)
      Low  rating after long resp → depth ↓
      High rating                → all dims nudge toward current
    """
    signals = [0.5] * N_DIMS

    # depth inference from reading behaviour
    if dwell_s > 60 and scroll_depth > 0.7:
        signals[DIM["depth"]] = 0.80
    elif dwell_s < 10 and scroll_depth < 0.30:
        signals[DIM["depth"]] = 0.20
    elif dwell_s > 30 and scroll_depth > 0.5:
        signals[DIM["depth"]] = 0.65

    # rating-based correction
    if rating is not None:
        if rating >= 4:
            # Good rating — reinforce all current dims (signal=0.5 is neutral/keep)
            pass
        elif rating <= 2 and response_len > 300:
            # Low rating on long response → wanted brevity
            signals[DIM["depth"]] = 0.15

    return signals


def merge_signals(
    query_sigs:    List[float],
    feedback_sigs: List[float],
    query_weight:  float = 0.6,
) -> List[float]:
    """
    Merge query signals (explicit intent) with feedback signals (implicit behaviour).
    Query signals take priority (higher weight).
    """
    w = query_weight
    return [w * q + (1-w) * f for q, f in zip(query_sigs, feedback_sigs)]


# ── EMA update ────────────────────────────────────────────────────────────────
def ema_update(
    current_vec: List[float],
    signal_vec:  List[float],
    alpha:       float = EMA_ALPHA,
) -> List[float]:
    """
    Apply EMA update to style vector.
    new[i] = alpha × signal[i] + (1−alpha) × current[i]
    """
    return [
        round(alpha * s + (1-alpha) * c, 4)
        for c, s in zip(current_vec, signal_vec)
    ]


# ── Vector → format dict ──────────────────────────────────────────────────────
@dataclass
class FormatPreferences:
    """Thresholded boolean decisions derived from style vector."""
    use_analogy:     bool
    use_example:     bool
    use_steps:       bool
    use_formula_box: bool
    use_visual_desc: bool
    use_memory_tip:  bool
    length:          str    # "brief" | "standard" | "detailed"
    max_words:       int


def vector_to_format(vec: List[float]) -> FormatPreferences:
    """Convert float style vector to binary format decisions used in prompt builder."""
    depth = vec[DIM["depth"]]

    if depth < 0.35:
        length, max_words = "brief",    120
    elif depth > 0.65:
        length, max_words = "detailed", 500
    else:
        length, max_words = "standard", 250

    return FormatPreferences(
        use_analogy     = vec[DIM["analogy"]]      > 0.55,
        use_example     = vec[DIM["example"]]      > 0.55,
        use_steps       = vec[DIM["step_by_step"]] > 0.50,
        use_formula_box = vec[DIM["formula_first"]]> 0.55,
        use_visual_desc = vec[DIM["visual"]]       > 0.60,
        use_memory_tip  = vec[DIM["memory_tip"]]   > 0.60,
        length          = length,
        max_words       = max_words,
    )


# ── Convenience ───────────────────────────────────────────────────────────────
def describe_vector(vec: List[float]) -> str:
    """Human-readable summary of a style vector (for logging/debug)."""
    names = ["visual","analogy","example","step_by_step","formula_first","depth","memory_tip"]
    parts = [f"{n}={v:.2f}" for n,v in zip(names,vec)]
    return "  ".join(parts)
