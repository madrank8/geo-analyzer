"""
Analyzer 4: Content Quality & E-E-A-T
Text statistics + E-E-A-T signals + optional NLP/Gemini enrichment.
Deterministic analysis ported from EntityOS content_engine.py TextAnalyzer.
"""
import math
import re
from collections import Counter

import httpx

from analyzers.base import AnalyzerBase
from google_apis.nlp import nlp_classify
from google_apis.gemini import gemini_score_dimensions

# AI-signature words (from EntityOS content_engine.py)
AI_SIGNATURE_WORDS = {
    "delve", "tapestry", "leverage", "landscape", "robust", "seamlessly",
    "multifaceted", "pivotal", "nuanced", "holistic", "paradigm",
    "transformative", "synergy", "cutting-edge", "game-changer",
    "groundbreaking", "innovative", "revolutionary", "unparalleled",
    "comprehensive", "streamline", "optimize", "utilize", "facilitate",
    "implement", "enhance", "spearhead", "foster", "cultivate",
    "empower", "realm", "unveil", "navigate", "underscore",
    "cornerstone", "testament", "embark", "intricate", "advent",
}

CLICHE_PHRASES = [
    "at the end of the day", "in today's world", "it goes without saying",
    "needless to say", "when it comes to", "in terms of", "the fact that",
    "in order to", "as a matter of fact", "last but not least",
    "it is worth noting", "it is important to note", "moving forward",
    "at the forefront", "a wide range of", "plays a crucial role",
]


def compute_text_stats(text: str) -> dict:
    """Compute deterministic text statistics."""
    words = text.split()
    word_count = len(words)
    if word_count == 0:
        return {"word_count": 0}

    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    sent_count = max(len(sentences), 1)

    # Flesch-Kincaid Grade Level
    syllable_count = sum(_count_syllables(w) for w in words)
    fk_grade = 0.39 * (word_count / sent_count) + 11.8 * (syllable_count / word_count) - 15.59

    # Type-Token Ratio (lexical diversity)
    unique_words = set(w.lower() for w in words)
    ttr = len(unique_words) / word_count

    # Sentence length variance (syntactic burstiness)
    sent_lengths = [len(s.split()) for s in sentences]
    mean_len = sum(sent_lengths) / len(sent_lengths)
    variance = sum((l - mean_len) ** 2 for l in sent_lengths) / len(sent_lengths)
    burstiness = math.sqrt(variance)

    # Passive voice ratio
    passive_count = len(re.findall(
        r'\b(?:is|are|was|were|been|being)\s+\w+ed\b', text, re.I
    ))
    passive_ratio = passive_count / sent_count

    # AI-signature word density
    text_lower = text.lower()
    ai_word_count = sum(1 for w in AI_SIGNATURE_WORDS if w in text_lower)
    ai_density = ai_word_count / (word_count / 100) if word_count > 0 else 0

    # Cliche density
    cliche_count = sum(1 for phrase in CLICHE_PHRASES if phrase in text_lower)
    cliche_density = cliche_count / (word_count / 100) if word_count > 0 else 0

    # Transition word density
    transitions = len(re.findall(
        r'\b(?:however|therefore|furthermore|moreover|additionally|consequently|'
        r'nevertheless|meanwhile|subsequently|alternatively|specifically|'
        r'in contrast|on the other hand|as a result)\b', text, re.I
    ))
    transition_density = transitions / (word_count / 100) if word_count > 0 else 0

    return {
        "word_count": word_count,
        "sentence_count": sent_count,
        "fk_grade": round(fk_grade, 1),
        "type_token_ratio": round(ttr, 3),
        "burstiness": round(burstiness, 1),
        "passive_ratio": round(passive_ratio, 3),
        "ai_signature_density": round(ai_density, 2),
        "cliche_density": round(cliche_density, 2),
        "transition_density": round(transition_density, 2),
        "avg_sentence_length": round(mean_len, 1),
    }


def _count_syllables(word: str) -> int:
    word = word.lower().strip(".,!?;:'\"")
    if len(word) <= 2:
        return 1
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def detect_eeat_signals(html: str, text: str, meta_tags: dict) -> dict:
    """Detect E-E-A-T signals on the page."""
    signals = {}

    # Author byline
    signals["has_author"] = bool(re.search(
        r'(?:author|byline|written.by|reviewed.by)[":\s]+[A-Z][a-z]+\s+[A-Z][a-z]+', html
    ))

    # Schema author
    signals["has_schema_author"] = bool(re.search(
        r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"[A-Z]', html
    ))

    # Publication date
    signals["has_pub_date"] = bool(re.search(
        r'(?:datePublished|article:published_time)', html, re.I
    ))

    # Update date
    signals["has_update_date"] = bool(re.search(
        r'(?:dateModified|article:modified_time)', html, re.I
    ))

    # Citations/sources
    signals["has_citations"] = bool(re.search(
        r'(?:according to|source:|citation|reference|bibliography)', text, re.I
    ))

    # Original data
    signals["has_original_data"] = bool(re.search(
        r'(?:our (?:research|study|data|survey|analysis)|we (?:found|discovered|analyzed|conducted))',
        text, re.I
    ))

    # Credentials mentioned
    signals["has_credentials"] = bool(re.search(
        r'(?:PhD|M\.D\.|certified|licensed|accredited|board.certified)', text, re.I
    ))

    return signals


class ContentQualityAnalyzer(AnalyzerBase):
    name = "content_quality"

    async def analyze(self, page_data: dict, business_type: str, api_keys: dict = None) -> dict:
        text = page_data.get("text_content", "")
        html = page_data.get("html", "")
        meta_tags = page_data.get("meta_tags", {})
        findings = []
        recommendations = []

        # ── Deterministic: Text stats ──
        stats = compute_text_stats(text)

        # ── Deterministic: E-E-A-T signals ──
        eeat = detect_eeat_signals(html, text, meta_tags)

        # ── Optional: Google NLP ──
        nlp_data = {}
        gemini_dimensions = {}
        api_keys = api_keys or {}
        if api_keys.get("nlp_api_key") or api_keys.get("kg_api_key"):
            async with httpx.AsyncClient() as client:
                nlp_data = await nlp_classify(text, client)

        # ── Optional: Gemini dimension scoring ──
        if api_keys.get("gemini_api_key"):
            async with httpx.AsyncClient() as client:
                gemini_result = await gemini_score_dimensions(stats, nlp_data, text, client)
                if gemini_result.get("status") == "success":
                    gemini_dimensions = gemini_result.get("dimensions", {})

        # ── Scoring ──
        score = 0

        # Text stats scoring (40 points)
        if stats.get("word_count", 0) > 300:
            score += 10
        if stats.get("word_count", 0) > 800:
            score += 5

        # Reading level (prefer 8-12 grade)
        fk = stats.get("fk_grade", 0)
        if 8 <= fk <= 12:
            score += 10
        elif 6 <= fk <= 14:
            score += 5

        # Lexical diversity (0.4-0.7 is ideal)
        ttr = stats.get("type_token_ratio", 0)
        if 0.4 <= ttr <= 0.7:
            score += 8
        elif 0.3 <= ttr <= 0.8:
            score += 4

        # Low AI signature density is good
        if stats.get("ai_signature_density", 0) < 0.5:
            score += 7
        elif stats.get("ai_signature_density", 0) < 1.0:
            score += 3
        else:
            findings.append({"severity": "medium", "title": "High AI-Signature Word Density",
                            "description": f"AI-signature word density: {stats['ai_signature_density']:.1f} per 100 words"})
            recommendations.append("Replace AI-signature words (delve, leverage, landscape, robust) with natural language")

        # E-E-A-T scoring (30 points)
        eeat_score = 0
        if eeat["has_author"]:
            eeat_score += 8
        else:
            findings.append({"severity": "medium", "title": "No Author Byline",
                            "description": "No visible author attribution found."})
            recommendations.append("Add author bylines with credentials to content pages")

        if eeat["has_pub_date"]:
            eeat_score += 5
        if eeat["has_update_date"]:
            eeat_score += 5
        if eeat["has_citations"]:
            eeat_score += 5
        if eeat["has_original_data"]:
            eeat_score += 7
        if eeat["has_credentials"]:
            eeat_score += 5
        score += min(30, eeat_score)

        # Gemini enrichment bonus (up to 20 points)
        if gemini_dimensions:
            dim_scores = []
            for dim_name, dim_data in gemini_dimensions.items():
                if isinstance(dim_data, dict):
                    dim_scores.append(dim_data.get("score", 50))
                elif isinstance(dim_data, (int, float)):
                    dim_scores.append(dim_data)
            if dim_scores:
                avg_gemini = sum(dim_scores) / len(dim_scores)
                score += int(avg_gemini * 0.2)

        # NLP enrichment bonus (up to 10 points)
        if nlp_data.get("status") == "success":
            entities = nlp_data.get("entities", [])
            if len(entities) >= 3:
                score += 5
            if any(e.get("mid") for e in entities):
                score += 5

        score = min(100, score)

        return {
            "scores": {"content_eeat": score},
            "findings": findings,
            "recommendations": recommendations,
            "details": {
                "text_stats": stats,
                "eeat_signals": eeat,
                "nlp_data": nlp_data if nlp_data.get("status") == "success" else None,
                "gemini_dimensions": gemini_dimensions or None,
            },
        }
