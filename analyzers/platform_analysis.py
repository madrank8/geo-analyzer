"""
Analyzer 2: Platform Analysis
Per-platform readiness scoring for AI search platforms.
"""
import re
from analyzers.base import AnalyzerBase


# Platform-specific scoring factors
PLATFORM_FACTORS = {
    "Google AI Overviews": {
        "crawlers": ["GoogleOther", "Google-Extended"],
        "schema_boost": ["Article", "FAQPage", "HowTo", "Organization", "LocalBusiness"],
        "weight_schema": 0.25,
        "weight_content": 0.35,
        "weight_crawler": 0.20,
        "weight_technical": 0.20,
    },
    "ChatGPT": {
        "crawlers": ["GPTBot", "OAI-SearchBot", "ChatGPT-User"],
        "schema_boost": ["Article", "Organization", "Product"],
        "weight_schema": 0.15,
        "weight_content": 0.40,
        "weight_crawler": 0.30,
        "weight_technical": 0.15,
    },
    "Perplexity": {
        "crawlers": ["PerplexityBot"],
        "schema_boost": ["Article", "FAQPage"],
        "weight_schema": 0.15,
        "weight_content": 0.40,
        "weight_crawler": 0.30,
        "weight_technical": 0.15,
    },
    "Gemini": {
        "crawlers": ["Google-Extended", "GoogleOther"],
        "schema_boost": ["Article", "Organization", "LocalBusiness", "Product"],
        "weight_schema": 0.25,
        "weight_content": 0.35,
        "weight_crawler": 0.15,
        "weight_technical": 0.25,
    },
    "Bing Copilot": {
        "crawlers": ["CCBot"],
        "schema_boost": ["Article", "Organization", "Product", "FAQPage"],
        "weight_schema": 0.20,
        "weight_content": 0.30,
        "weight_crawler": 0.25,
        "weight_technical": 0.25,
    },
}


class PlatformAnalyzer(AnalyzerBase):
    name = "platform_analysis"

    async def analyze(self, page_data: dict, business_type: str, api_keys: dict = None) -> dict:
        html = page_data.get("html", "")
        structured_data = page_data.get("structured_data", [])
        has_ssr = page_data.get("has_ssr_content", True)
        crawler_status = page_data.get("_crawler_status", {})  # passed from ai_visibility
        findings = []
        recommendations = []

        # Extract schema types present
        schema_types = set()
        for sd in structured_data:
            if isinstance(sd, dict):
                t = sd.get("@type", "")
                if isinstance(t, list):
                    schema_types.update(t)
                else:
                    schema_types.add(t)

        # Check for sameAs links
        has_same_as = bool(re.search(r'"sameAs"', html))

        # Check for IndexNow
        has_indexnow = bool(re.search(r'indexnow', html, re.I))

        # Content quality signals (simple heuristics)
        word_count = page_data.get("word_count", 0)
        has_headings = len(page_data.get("heading_structure", [])) > 2
        has_meta_desc = bool(page_data.get("description"))

        content_score = 0
        if word_count > 300:
            content_score += 25
        if word_count > 800:
            content_score += 15
        if word_count > 1500:
            content_score += 10
        if has_headings:
            content_score += 20
        if has_meta_desc:
            content_score += 15
        if has_same_as:
            content_score += 15
        content_score = min(100, content_score)

        # Technical score
        tech_score = 0
        if has_ssr:
            tech_score += 40
        if page_data.get("canonical"):
            tech_score += 15
        if page_data.get("security_headers", {}).get("Strict-Transport-Security"):
            tech_score += 15
        if has_indexnow:
            tech_score += 15
        if page_data.get("meta_tags", {}).get("viewport"):
            tech_score += 15
        tech_score = min(100, tech_score)

        # Score per platform
        platform_scores = {}
        for platform, factors in PLATFORM_FACTORS.items():
            # Crawler score for this platform
            platform_crawler_score = 0
            for crawler in factors["crawlers"]:
                status = crawler_status.get(crawler, "NOT_MENTIONED")
                if "ALLOW" in status or status in ("NOT_MENTIONED", "NO_ROBOTS_TXT"):
                    platform_crawler_score += 100 // len(factors["crawlers"])
                elif status == "PARTIALLY_BLOCKED":
                    platform_crawler_score += 50 // len(factors["crawlers"])

            # Schema score for this platform
            schema_score = 0
            matched_schemas = schema_types & set(factors["schema_boost"])
            if matched_schemas:
                schema_score = min(100, len(matched_schemas) * 30)
            if has_same_as:
                schema_score = min(100, schema_score + 20)

            # Weighted composite
            score = int(
                schema_score * factors["weight_schema"] +
                content_score * factors["weight_content"] +
                platform_crawler_score * factors["weight_crawler"] +
                tech_score * factors["weight_technical"]
            )
            platform_scores[platform] = min(100, score)

        # Findings
        low_platforms = [p for p, s in platform_scores.items() if s < 40]
        if low_platforms:
            findings.append({
                "severity": "high",
                "title": f"Low Readiness on {len(low_platforms)} Platform(s)",
                "description": f"Below 40/100: {', '.join(low_platforms)}",
            })

        if not has_ssr:
            recommendations.append("Implement server-side rendering for AI crawler access")
        if not has_same_as:
            recommendations.append("Add sameAs links in Organization schema to connect platform profiles")

        overall = int(sum(platform_scores.values()) / max(len(platform_scores), 1))

        return {
            "scores": {"platform_optimization": overall},
            "findings": findings,
            "recommendations": recommendations,
            "details": {
                "platforms": platform_scores,
                "content_score": content_score,
                "technical_score": tech_score,
            },
        }
