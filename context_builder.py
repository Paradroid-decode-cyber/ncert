"""
context_builder.py  —  pctx assembly + personalized prompt builder

build_pctx()     assembles all 15+ fields from all engines into one dict
build_prompt()   converts pctx → natural-language LLM directives (14 sections)
"""
from __future__ import annotations

import time
import logging
from typing import Dict, List, Optional

from bkt_engine import BKTEngine
from style_engine import (vector_to_format, query_signals, feedback_signals, merge_signals)

from interest_engine import evaluate_state

log = logging.getLogger("context_builder")

NEUTRAL_VEC   = [0.5] * 7
COLD_START_N  = 5


# ══════════════════════════════════════════════════════════════════════════════
# pctx assembly
# ══════════════════════════════════════════════════════════════════════════════
def build_pctx(
    profile:   dict,
    session:   "SessionData",          # noqa: F821  (avoid circular import)
    query:     str,
    topic:     str,
    bkt:       BKTEngine,
    dwell_s:   float = 0.0,
    scroll:    float = 0.5,
    rating:    Optional[int] = None,
    prev_resp_len: int = 0,
) -> dict:
    """
    Assemble the full personalization context dictionary.

    Called by pipeline node 3 (build_pctx).

    pctx is then passed through:
      → retrieve_rag       (grade filter)
      → run_guardrails     (may override fields)
      → generate           (prompt builder reads pctx)
      → flush_to_db        (EMA update uses style signals)
    """
    user_id = profile["user_id"]
    grade   = profile.get("grade", 10)

    # ── Style signals ─────────────────────────────────────────────
    q_sigs = query_signals(query)
    f_sigs = feedback_signals(dwell_s, scroll, rating, prev_resp_len)
    merged = merge_signals(q_sigs, f_sigs)

    current_vec = profile.get("style_vector", NEUTRAL_VEC)
    fmt         = vector_to_format(current_vec)

    # ── BKT mastery ───────────────────────────────────────────────
    mastery_score               = bkt.get_mastery(user_id, topic)
    zpd, _                      = bkt.get_zpd(user_id, topic)
    can_proceed, missing_prereqs= bkt.check_prerequisites(user_id, topic)
    all_mastery                 = bkt.get_all_mastery(user_id)
    avg_mastery                 = bkt.get_avg_mastery(user_id)

    # ── Interest state ────────────────────────────────────────────
    interest = evaluate_state(
        query                  = query,
        consecutive_low_ratings= session.consecutive_low_ratings,
        current_mastery        = mastery_score,
        dwell_times_s          = session.dwell_times_s,
        scroll_depths          = session.scroll_depths,
        follow_up_count        = session.follow_up_count,
        query_count            = session.query_count,
        existing_exam_mode     = session.exam_mode,
    )

    # ── Assemble pctx ─────────────────────────────────────────────
    pctx: dict = {
        # Identity
        "user_id":      user_id,
        "grade":        grade,
        "board":        profile.get("board", "CBSE"),
        "language":     session.language_override or profile.get("preferred_language", "en"),
        "target_exams": profile.get("target_exams", []),
        "school_type":  profile.get("school_type", ""),

        # Topic
        "topic":        topic,
        "subject":      session.active_subject or profile.get("top_subjects", [""])[0],
        "chapter":      session.active_chapter,

        # Mastery
        "mastery": {
            "topic":      round(mastery_score, 3),
            "avg":        round(avg_mastery, 3),
            "all_topics": {k: round(v,3) for k,v in all_mastery.items()},
        },

        # Difficulty / ZPD
        "difficulty":       zpd,
        "can_proceed":      can_proceed,
        "missing_prereqs":  missing_prereqs,

        # Style
        "style_vector": current_vec,
        "_style_signals": merged,    # stored for EMA update in flush_to_db

        # Format (derived from style_vector)
        "format": {
            "use_analogy":     fmt.use_analogy,
            "use_example":     fmt.use_example,
            "use_steps":       fmt.use_steps,
            "use_formula_box": fmt.use_formula_box,
            "use_visual_desc": fmt.use_visual_desc,
            "use_memory_tip":  fmt.use_memory_tip,
            "length":          fmt.length,
            "max_words":       fmt.max_words,
        },

        # Interest / state flags
        "exam_mode":     interest.exam_mode,
        "frustrated":    interest.frustrated,
        "bored":         interest.bored,
        "disengaged":    interest.disengaged,
        "high_interest": interest.high_interest,
        "interest_score":interest.interest_score,

        # Session context
        "session": {
            "query_count":             session.query_count,
            "consecutive_low_ratings": session.consecutive_low_ratings,
            "recent_topics":           session.recent_topics,
            "recent_errors":           session.recent_errors,
            "difficulty_adjustments":  session.difficulty_adjustments,
            "avg_dwell":               session.avg_dwell,
            "exam_mode":               session.exam_mode,
        },

        # Cold-start flag
        "is_cold_start": profile.get("total_queries", 0) < COLD_START_N,
        "total_queries": profile.get("total_queries", 0),
    }

    return pctx


# ══════════════════════════════════════════════════════════════════════════════
# Prompt builder
# ══════════════════════════════════════════════════════════════════════════════
def build_prompt(
    pctx:             dict,
    query:            str,
    context_text:     str       = "",
    source:           str       = "rag",
    source_refs:      List[str] = None,
    images:           List[dict]= None,
    prompt_additions: List[str] = None,
) -> str:
    """
    Build the full personalized prompt string.

    14-section structure (each section conditional on pctx):
      1.  Identity line
      2.  Source instruction
      3.  Difficulty directive
      4.  Style directives
      5.  Length instruction
      6.  Prereq bridge    (if missing_prereqs)
      7.  Frustration tone (if frustrated)
      8.  Exam mode        (if exam_mode)
      9.  Recent errors    (if any)
      10. Language         (if ≠ en)
      11. Image references (if images found)
      12. Guardrail additions
      13. === CONTEXT ===
      14. === STUDENT QUESTION ===
    """
    parts = []
    fmt = pctx.get("format", {})
    source_refs = source_refs or []
    images      = images      or []
    prompt_additions = prompt_additions or []

    # ── 1. Identity ───────────────────────────────────────────────
    exams = ", ".join(pctx.get("target_exams", [])) or None
    exam_str = f", preparing for {exams}" if exams else ""
    parts.append(
        f"You are a patient NCERT tutor for a Class {pctx['grade']} "
        f"{pctx.get('board','CBSE')} student{exam_str}. "
        f"Always use age-appropriate language."
    )

    # ── 2. Source instruction ─────────────────────────────────────
    if source == "rag":
        parts.append(
            "Answer ONLY using the NCERT content in the CONTEXT section below. "
            "Do not add information from general knowledge."
        )
    elif source == "web":
        parts.append(
            "Answer by summarising the web search results in CONTEXT below. "
            "Note: this content is from the web, not directly from the NCERT textbook."
        )
    else:
        parts.append("Answer from your general NCERT knowledge.")

    # ── 3. Difficulty directive ───────────────────────────────────
    diff = pctx.get("difficulty", "medium")
    mastery_pct = int(pctx.get("mastery", {}).get("topic", 0.5) * 100)
    diff_directives = {
        "easy":   f"DIFFICULTY: EASY — mastery {mastery_pct}%. Start from the very basics. Define all terms. Use the simplest language possible.",
        "medium": f"DIFFICULTY: MEDIUM — mastery {mastery_pct}%. Explain clearly with moderate depth. Skip very basic definitions.",
        "hard":   f"DIFFICULTY: HARD — mastery {mastery_pct}%. Use exam-level complexity. Include edge cases and derivations.",
    }
    parts.append(diff_directives.get(diff, diff_directives["medium"]))

    # ── 4. Style directives ───────────────────────────────────────
    style_parts = []
    if fmt.get("use_analogy"):     style_parts.append("Use a real-world analogy to explain the concept.")
    if fmt.get("use_example"):     style_parts.append("Include a concrete worked example.")
    if fmt.get("use_steps"):       style_parts.append("Break the explanation into numbered steps.")
    if fmt.get("use_formula_box"): style_parts.append("Present key formulas in a clear block before explanation.")
    if fmt.get("use_visual_desc"): style_parts.append("Describe any relevant diagram or figure in precise text.")
    if fmt.get("use_memory_tip"):  style_parts.append("Add a mnemonic or memory tip at the end.")
    if style_parts:
        parts.append("FORMAT: " + " ".join(style_parts))

    # ── 5. Length ─────────────────────────────────────────────────
    length = fmt.get("length", "standard")
    max_w  = fmt.get("max_words", 250)
    length_map = {
        "brief":    f"Keep response under {max_w} words. Be concise.",
        "standard": f"Aim for {max_w} words. Clear and complete.",
        "detailed": f"Provide a thorough explanation (~{max_w} words).",
    }
    parts.append(length_map.get(length, length_map["standard"]))

    # ── 6. Prereq bridge ─────────────────────────────────────────
    missing = pctx.get("missing_prereqs", [])
    if missing:
        parts.append(
            f"PREREQUISITE BRIDGE: The student hasn't fully mastered "
            f"{', '.join(missing)}. Spend 1-2 sentences explaining "
            f"the key idea from these topics before answering."
        )

    # ── 7. Frustration tone ───────────────────────────────────────
    if pctx.get("frustrated"):
        parts.append(
            "TONE: Student seems frustrated. Be especially warm and encouraging. "
            "Start with reassurance (e.g. 'This is a tricky topic — let's take it step by step')."
        )

    # ── 8. Exam mode ──────────────────────────────────────────────
    if pctx.get("exam_mode"):
        parts.append(
            "EXAM MODE: Highlight the most exam-important points. "
            "Include: key formula, one-line definition, and a typical exam question type."
        )

    # ── 9. Recent errors ─────────────────────────────────────────
    errors = pctx.get("session", {}).get("recent_errors", [])
    if errors:
        err_str = "; ".join(errors[:3])
        parts.append(
            f"PREVIOUS ERRORS: Student recently struggled with: {err_str}. "
            f"Address these if relevant to the current question."
        )

    # ── 10. Language ──────────────────────────────────────────────
    lang = pctx.get("language", "en")
    if lang and lang != "en":
        lang_names = {
            "hi":"Hindi","ta":"Tamil","te":"Telugu","mr":"Marathi",
            "bn":"Bengali","gu":"Gujarati","kn":"Kannada","ml":"Malayalam",
        }
        parts.append(
            f"LANGUAGE: Write your response in {lang_names.get(lang, lang.upper())}. "
            f"Keep all scientific terms, formulas, and proper nouns in English."
        )

    # ── 11. Image references ──────────────────────────────────────
    if images:
        img_refs = "\n".join(
            f"  [Image {i+1}: {img.get('caption','')[:120]} — Page {img.get('page','')}]"
            for i, img in enumerate(images[:3])
        )
        parts.append(f"RELEVANT FIGURES:\n{img_refs}\nReference these figures in your explanation where appropriate.")

    # ── 12. Guardrail additions ───────────────────────────────────
    for addition in prompt_additions:
        parts.append(addition)

    # ── 13. Context ───────────────────────────────────────────────
    if context_text:
        if source_refs:
            refs_str = " | ".join(source_refs[:3])
            parts.append(f"\n=== CONTEXT (from: {refs_str}) ===\n{context_text.strip()}\n=== END CONTEXT ===")
        else:
            parts.append(f"\n=== CONTEXT ===\n{context_text.strip()}\n=== END CONTEXT ===")

    # ── 14. Question ─────────────────────────────────────────────
    parts.append(f"\n=== STUDENT QUESTION ===\n{query.strip()}")

    return "\n\n".join(parts)


def build_system_prompt(pctx: dict) -> str:
    """Short system message (used only in cloud mode)."""
    grade   = pctx.get("grade", 10)
    board   = pctx.get("board", "CBSE")
    subject = pctx.get("subject", "Science")
    return (
        f"You are an expert NCERT {subject} tutor for Class {grade} {board}. "
        f"You are encouraging, clear, and curriculum-accurate. "
        f"Never make up facts. If unsure, say so."
    )
