"""
guardrails.py  —  10 personalization safety checks

Each guardrail inspects pctx and may:
  1. Override pctx fields (difficulty, format, style)
  2. Inject text into prompt_additions
  3. Hard-block generation (blocked=True) and return safe fallback

Order matters — run sequentially. Later guardrails can override earlier ones.

Guardrails:
  1.  cold_start         — neutral until 5 queries
  2.  difficulty_cliff   — max 1 ZPD level jump per session
  3.  frustration_cb     — circuit breaker: easy+empathetic after 3 bad ratings
  4.  prereq_gate        — inject bridging text for missing prerequisites
  5.  confidence_floor   — block generation if RAG score < 0.30 + no web
  6.  hallucination_guard— enforce strict citation mode for low-confidence sources
  7.  exam_mode_boost    — force formula + steps format when exam_mode=True
  8.  boredom_challenge  — add harder extension question when bored
  9.  language_check     — add translation directive for non-English users
  10. off_topic_guard    — detect and redirect clearly off-topic queries
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("guardrails")

# ── Thresholds ────────────────────────────────────────────────────────────────
COLD_START_MIN_QUERIES = 5
CONFIDENCE_FLOOR       = 0.30
FRUSTRATION_TRIGGER    = 3

_DIFF_ORDER = ["easy", "medium", "hard"]

_OFF_TOPIC_PATTERNS = [
    r"\b(recipe|cook|food|weather|sport|cricket|ipl|movie|film|song|music|actor|actress)\b",
    r"\b(girlfriend|boyfriend|love|crush|relationship|dating)\b",
    r"\b(hack|crack|cheat code|bypass|illegal)\b",
]


# ── Report ────────────────────────────────────────────────────────────────────
@dataclass
class GuardrailReport:
    triggered:        List[str]     = field(default_factory=list)
    overrides:        Dict          = field(default_factory=dict)
    prompt_additions: List[str]     = field(default_factory=list)
    blocked:          bool          = False
    block_reason:     str           = ""
    safe_response:    str           = ""


# ══════════════════════════════════════════════════════════════════════════════
# Individual guardrails
# ══════════════════════════════════════════════════════════════════════════════

def _guardrail_cold_start(pctx: dict, report: GuardrailReport):
    """Reset to neutral personalization until enough signal is gathered."""
    if pctx.get("total_queries", 0) < COLD_START_MIN_QUERIES:
        report.triggered.append("cold_start")
        pctx["style_vector"] = [0.5] * 7
        pctx["difficulty"]   = "medium"
        pctx["is_cold_start"]= True
        report.overrides["difficulty"] = "medium (cold start)"


def _guardrail_difficulty_cliff(pctx: dict, report: GuardrailReport):
    """
    Prevent jumping more than 1 difficulty level per session.
    Reads difficulty_adjustments from session to know last difficulty used.
    """
    adjustments = pctx.get("session", {}).get("difficulty_adjustments", [])
    if not adjustments:
        return

    last = adjustments[-1] if adjustments else "medium"
    current = pctx.get("difficulty", "medium")

    if last not in _DIFF_ORDER or current not in _DIFF_ORDER:
        return

    last_idx    = _DIFF_ORDER.index(last)
    current_idx = _DIFF_ORDER.index(current)

    if abs(current_idx - last_idx) > 1:
        # Clamp to max 1 step
        clamped = _DIFF_ORDER[last_idx + (1 if current_idx > last_idx else -1)]
        report.triggered.append("difficulty_cliff")
        pctx["difficulty"] = clamped
        report.overrides["difficulty"] = f"clamped {current}→{clamped} (cliff prevention)"
        log.debug(f"Difficulty cliff: {current}→{clamped}")


def _guardrail_frustration_cb(pctx: dict, report: GuardrailReport):
    """Circuit breaker: if 3+ consecutive low ratings, force easy+empathetic."""
    if pctx.get("session", {}).get("consecutive_low_ratings", 0) >= FRUSTRATION_TRIGGER:
        report.triggered.append("frustration_cb")
        pctx["difficulty"]            = "easy"
        pctx["frustrated"]            = True
        pctx["format"]["length"]      = "brief"
        pctx["format"]["use_analogy"] = True
        report.overrides["difficulty"] = "easy (frustration circuit breaker)"
        report.prompt_additions.append(
            "TONE: Student seems frustrated. Open with: 'Don't worry — this confuses many students!' "
            "Be extra gentle, skip jargon, use the simplest possible language."
        )


def _guardrail_prereq_gate(pctx: dict, report: GuardrailReport):
    """Inject prerequisite bridging text if missing prereqs detected."""
    if not pctx.get("can_proceed", True):
        missing = pctx.get("missing_prereqs", [])
        if missing:
            report.triggered.append("prereq_gate")
            prereq_str = " and ".join(missing)
            report.prompt_additions.append(
                f"PREREQUISITE BRIDGE: Before answering, spend 2 sentences "
                f"explaining {prereq_str} in simple terms, "
                f"since the student hasn't mastered these yet."
            )


def _guardrail_confidence_floor(
    pctx:       dict,
    report:     GuardrailReport,
    confidence: float,
    source:     str,
):
    """Block generation if confidence too low and no web fallback."""
    if confidence < CONFIDENCE_FLOOR and source == "none":
        report.triggered.append("confidence_floor")
        report.blocked       = True
        report.block_reason  = f"confidence={confidence:.2f} below floor={CONFIDENCE_FLOOR}"
        report.safe_response = (
            "I don't have reliable information about this specific topic in my NCERT database. "
            "Please check your textbook directly, or try rephrasing the question with "
            "the chapter name included."
        )


def _guardrail_hallucination_guard(
    pctx:       dict,
    report:     GuardrailReport,
    confidence: float,
    source:     str,
):
    """Enforce strict citation mode for low-confidence or web sources."""
    if source == "web" or (confidence < 0.60 and source == "rag"):
        report.triggered.append("hallucination_guard")
        report.prompt_additions.append(
            "CITATION RULE: Only state facts present in the CONTEXT below. "
            "If unsure, say 'According to the source...' rather than stating as fact. "
            "Do NOT add information from general knowledge."
        )


def _guardrail_exam_mode_boost(pctx: dict, report: GuardrailReport):
    """Force formula-forward, structured format in exam mode."""
    if pctx.get("exam_mode"):
        report.triggered.append("exam_mode_boost")
        pctx["format"]["use_formula_box"] = True
        pctx["format"]["use_steps"]       = True
        pctx["format"]["length"]          = "detailed"
        report.prompt_additions.append(
            "EXAM MODE: Student is preparing for an exam. "
            "Start with the key formula(s) in a box. "
            "Then give a concise explanation. "
            "End with 1-2 typical exam-style questions on this topic."
        )


def _guardrail_boredom_challenge(pctx: dict, report: GuardrailReport):
    """Add extension question for bored/advanced students."""
    if pctx.get("bored") and not pctx.get("frustrated"):
        report.triggered.append("boredom_challenge")
        report.prompt_additions.append(
            "CHALLENGE: Student has high mastery on this topic. "
            "After your main answer, add a 'THINK FURTHER' section with "
            "one harder, exam-level extension question to stretch their thinking."
        )


def _guardrail_language_check(pctx: dict, report: GuardrailReport):
    """Add translation directive for non-English preferred language."""
    lang = pctx.get("language", "en")
    if lang and lang != "en":
        lang_names = {
            "hi": "Hindi", "ta": "Tamil", "te": "Telugu",
            "mr": "Marathi","bn": "Bengali","gu": "Gujarati",
            "kn": "Kannada","ml": "Malayalam","pa": "Punjabi",
        }
        lang_name = lang_names.get(lang, lang.upper())
        report.triggered.append("language_check")
        report.prompt_additions.append(
            f"LANGUAGE: Respond in {lang_name}. "
            f"Keep all scientific terms, formulas, and proper nouns in English."
        )


def _guardrail_off_topic_guard(
    pctx:   dict,
    report: GuardrailReport,
    query:  str,
):
    """Detect and redirect clearly off-topic queries."""
    q = query.lower()
    for pattern in _OFF_TOPIC_PATTERNS:
        if re.search(pattern, q):
            report.triggered.append("off_topic_guard")
            report.blocked      = True
            report.block_reason = "off-topic query detected"
            subject = pctx.get("active_subject", "your subject")
            report.safe_response = (
                f"I'm specialised in NCERT curriculum topics for Class {pctx.get('grade','10')}. "
                f"That question seems outside my area. "
                f"Feel free to ask me anything about {subject} or other NCERT subjects!"
            )
            return


# ══════════════════════════════════════════════════════════════════════════════
# Master run_guardrails
# ══════════════════════════════════════════════════════════════════════════════
def run_guardrails(
    pctx:       dict,
    query:      str       = "",
    confidence: float     = 1.0,
    source:     str       = "rag",
) -> Tuple[dict, GuardrailReport]:
    """
    Run all 10 guardrails sequentially.

    Modifies pctx in-place for overrides.
    Returns (modified_pctx, report).

    Stop early on block — no point continuing.
    """
    report = GuardrailReport()

    # ── Run in order ──────────────────────────────────────────────
    _guardrail_off_topic_guard(pctx, report, query)
    if report.blocked: return pctx, report

    _guardrail_confidence_floor(pctx, report, confidence, source)
    if report.blocked: return pctx, report

    _guardrail_cold_start(pctx, report)
    _guardrail_difficulty_cliff(pctx, report)
    _guardrail_frustration_cb(pctx, report)
    _guardrail_prereq_gate(pctx, report)
    _guardrail_hallucination_guard(pctx, report, confidence, source)
    _guardrail_exam_mode_boost(pctx, report)
    _guardrail_boredom_challenge(pctx, report)
    _guardrail_language_check(pctx, report)

    if report.triggered:
        log.debug(f"Guardrails triggered: {report.triggered}")

    return pctx, report
