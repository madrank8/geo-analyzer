"""
Analyzer 1: AI Visibility
- Citability scoring (from geo-seo-claude citability_scorer.py)
- AI crawler access (from robots.txt)
- llms.txt validation
- Brand mention scanning
"""
import re
from typing import Optional

import httpx

from analyzers.base import AnalyzerBase
from discovery.fetcher import fetch_robots_txt, fetch_llms_txt, extract_content_blocks


def score_passage(text: str, heading: Optional[str] = None) -> dict:
    """Score a single passage for AI citability (0-100)."""
    words = text.split()
    word_count = len(words)

    scores = {
        "answer_block_quality": 0,
        "self_containment": 0,
        "structural_readability": 0,
        "statistical_density": 0,
        "uniqueness_signals": 0,
    }

    # === 1. Answer Block Quality (30%) ===
    abq_score = 0
    definition_patterns = [
        r"\b\w+\s+is\s+(?:a|an|the)\s",
        r"\b\w+\s+refers?\s+to\s",
        r"\b\w+\s+means?\s",
        r"\b\w+\s+(?:can be |are )?defined\s+as\s",
    ]
    for pattern in definition_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            abq_score += 15
            break

    first_60_words = " ".join(words[:60])
    if any(re.search(p, first_60_words, re.IGNORECASE)
           for p in [r"\b(?:is|are|was|were|means?|refers?)\b", r"\d+%", r"\$[\d,]+",
                     r"\d+\s+(?:million|billion|thousand)"]):
        abq_score += 15

    if heading and heading.endswith("?"):
        abq_score += 10

    sentences = re.split(r"[.!?]+", text)
    short_clear = sum(1 for s in sentences if 5 <= len(s.split()) <= 25)
    if sentences:
        abq_score += int((short_clear / len(sentences)) * 10)

    if re.search(r"(?:according to|research shows|studies? (?:show|indicate|suggest|found))", text, re.I):
        abq_score += 10

    scores["answer_block_quality"] = min(abq_score, 30)

    # === 2. Self-Containment (25%) ===
    sc_score = 0
    if 134 <= word_count <= 167:
        sc_score += 10
    elif 100 <= word_count <= 200:
        sc_score += 7
    elif 80 <= word_count <= 250:
        sc_score += 4
    elif word_count >= 30:
        sc_score += 2

    pronoun_count = len(re.findall(
        r"\b(?:it|they|them|their|this|that|these|those|he|she|his|her)\b", text, re.I
    ))
    if word_count > 0:
        pronoun_ratio = pronoun_count / word_count
        if pronoun_ratio < 0.02:
            sc_score += 8
        elif pronoun_ratio < 0.04:
            sc_score += 5
        elif pronoun_ratio < 0.06:
            sc_score += 3

    proper_nouns = len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text))
    if proper_nouns >= 3:
        sc_score += 7
    elif proper_nouns >= 1:
        sc_score += 4

    scores["self_containment"] = min(sc_score, 25)

    # === 3. Structural Readability (20%) ===
    sr_score = 0
    if sentences:
        avg_len = word_count / len(sentences)
        if 10 <= avg_len <= 20:
            sr_score += 8
        elif 8 <= avg_len <= 25:
            sr_score += 5
        else:
            sr_score += 2

    if re.search(r"(?:first|second|third|finally|additionally|moreover)", text, re.I):
        sr_score += 4
    if re.search(r"(?:\d+[\.\)]\s|\b(?:step|tip|point)\s+\d+)", text, re.I):
        sr_score += 4
    if "\n" in text:
        sr_score += 4

    scores["structural_readability"] = min(sr_score, 20)

    # === 4. Statistical Density (15%) ===
    sd_score = 0
    sd_score += min(len(re.findall(r"\d+(?:\.\d+)?%", text)) * 3, 6)
    sd_score += min(len(re.findall(r"\$[\d,]+(?:\.\d+)?", text)) * 3, 5)
    sd_score += min(len(re.findall(
        r"\b\d+(?:,\d{3})*(?:\.\d+)?\s+(?:users|customers|pages|sites|companies|people|percent|times)",
        text, re.I)) * 2, 4)
    if re.findall(r"\b20(?:2[3-6]|1\d)\b", text):
        sd_score += 2
    for pattern in [r"(?:according to|per|from|by)\s+[A-Z]",
                    r"(?:Gartner|Forrester|McKinsey|Harvard|Google|Microsoft|OpenAI|Anthropic)"]:
        if re.search(pattern, text):
            sd_score += 2

    scores["statistical_density"] = min(sd_score, 15)

    # === 5. Uniqueness Signals (10%) ===
    us_score = 0
    if re.search(r"(?:our (?:research|study|data|analysis)|we (?:found|discovered|analyzed))", text, re.I):
        us_score += 5
    if re.search(r"(?:case study|for example|for instance|real-world)", text, re.I):
        us_score += 3
    if re.search(r"(?:using|with|via)\s+[A-Z][a-z]+", text):
        us_score += 2

    scores["uniqueness_signals"] = min(us_score, 10)

    total = sum(scores.values())
    if total >= 80:
        grade, label = "A", "Highly Citable"
    elif total >= 65:
        grade, label = "B", "Good Citability"
    elif total >= 50:
        grade, label = "C", "Moderate Citability"
    elif total >= 35:
        grade, label = "D", "Low Citability"
    else:
        grade, label = "F", "Poor Citability"

    return {
        "heading": heading, "word_count": word_count, "total_score": total,
        "grade": grade, "label": label, "breakdown": scores,
        "preview": " ".join(words[:30]) + ("..." if word_count > 30 else ""),
    }


class AIVisibilityAnalyzer(AnalyzerBase):
    name = "ai_visibility"

    async def analyze(self, page_data: dict, business_type: str, api_keys: dict = None) -> dict:
        url = page_data["url"]
        html = page_data.get("html", "")
        findings = []
        recommendations = []

        # ── 1. Citability scoring ──
        blocks = extract_content_blocks(html)
        scored_blocks = [score_passage(b["content"], b.get("heading")) for b in blocks]

        avg_citability = 0
        optimal_count = 0
        if scored_blocks:
            avg_citability = sum(b["total_score"] for b in scored_blocks) / len(scored_blocks)
            optimal_count = sum(1 for b in scored_blocks if 134 <= b["word_count"] <= 167)

        grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for b in scored_blocks:
            grade_dist[b["grade"]] += 1

        if avg_citability < 40:
            findings.append({
                "severity": "high",
                "title": "Low AI Citability",
                "description": f"Average citability score is {avg_citability:.0f}/100. Content blocks are not optimized for AI citation.",
            })
            recommendations.append("Restructure content into self-contained 134-167 word passages with clear answers")

        # ── 2. AI Crawler access ──
        robots_data = await fetch_robots_txt(url)
        crawler_status = robots_data.get("ai_crawler_status", {})
        blocked_crawlers = [c for c, s in crawler_status.items() if "BLOCK" in s]
        allowed_crawlers = [c for c, s in crawler_status.items() if "ALLOW" in s or s == "NOT_MENTIONED" or s == "NO_ROBOTS_TXT"]

        if len(blocked_crawlers) > 3:
            findings.append({
                "severity": "critical",
                "title": f"{len(blocked_crawlers)} AI Crawlers Blocked",
                "description": f"Blocked: {', '.join(blocked_crawlers[:5])}. This prevents AI platforms from citing your content.",
            })
            recommendations.append("Unblock major AI crawlers (GPTBot, ClaudeBot, PerplexityBot) in robots.txt")

        crawler_score = min(100, int((len(allowed_crawlers) / max(len(crawler_status), 1)) * 100))

        # ── 3. llms.txt validation ──
        llms_data = await fetch_llms_txt(url)
        has_llms = llms_data["llms_txt"]["exists"]
        has_llms_full = llms_data["llms_full_txt"]["exists"]

        llms_score = 0
        if has_llms:
            llms_score += 60
            content = llms_data["llms_txt"]["content"]
            if len(content) > 100:
                llms_score += 20
            if "http" in content:
                llms_score += 20
        else:
            findings.append({
                "severity": "medium",
                "title": "Missing llms.txt",
                "description": "No llms.txt file found. This file helps AI systems understand your key content.",
            })
            recommendations.append("Create /llms.txt with title, description, and links to key pages")

        if has_llms_full:
            llms_score = min(100, llms_score + 20)

        # ── Composite score ──
        citability_score = min(100, int(avg_citability * 1.2))
        ai_visibility_score = int(
            citability_score * 0.50 +
            crawler_score * 0.35 +
            llms_score * 0.15
        )

        return {
            "scores": {"ai_citability": ai_visibility_score},
            "findings": findings,
            "recommendations": recommendations,
            "details": {
                "citability": {
                    "average_score": round(avg_citability, 1),
                    "total_blocks": len(scored_blocks),
                    "optimal_length_blocks": optimal_count,
                    "grade_distribution": grade_dist,
                    "top_blocks": sorted(scored_blocks, key=lambda x: x["total_score"], reverse=True)[:5],
                },
                "crawlers": {
                    "status": crawler_status,
                    "blocked": blocked_crawlers,
                    "allowed": allowed_crawlers,
                    "score": crawler_score,
                    "robots_exists": robots_data["exists"],
                    "sitemaps": robots_data.get("sitemaps", []),
                },
                "llms_txt": {
                    "exists": has_llms,
                    "full_exists": has_llms_full,
                    "score": llms_score,
                },
            },
        }
