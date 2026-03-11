"""
GEO Composite Scorer — Computes the overall GEO Readiness Score (0-100).
"""

WEIGHTS = {
    "ai_citability": 0.25,
    "brand_authority": 0.20,
    "content_eeat": 0.20,
    "technical": 0.15,
    "schema": 0.10,
    "platform_optimization": 0.10,
}


def compute_geo_score(analyzer_results: dict) -> dict:
    """
    Compute the composite GEO score from individual analyzer scores.

    Args:
        analyzer_results: dict with keys matching WEIGHTS, values 0-100

    Returns:
        {"geo_score": int, "scores": dict, "weights": dict, "grade": str, "label": str}
    """
    category_scores = {}
    for category in WEIGHTS:
        category_scores[category] = analyzer_results.get(category, 0)

    geo_score = sum(
        score * WEIGHTS[cat]
        for cat, score in category_scores.items()
    )
    geo_score = round(min(100, max(0, geo_score)))

    # Grade
    if geo_score >= 85:
        grade, label = "A", "Excellent"
    elif geo_score >= 70:
        grade, label = "B", "Good"
    elif geo_score >= 55:
        grade, label = "C", "Moderate"
    elif geo_score >= 40:
        grade, label = "D", "Below Average"
    else:
        grade, label = "F", "Needs Attention"

    return {
        "geo_score": geo_score,
        "scores": category_scores,
        "weights": WEIGHTS,
        "grade": grade,
        "label": label,
    }


def generate_action_plan(findings: list, scores: dict) -> dict:
    """Generate a prioritized action plan from findings and scores."""
    quick_wins = []
    medium_term = []
    strategic = []

    # Sort findings by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.get("severity", "info"), 4))

    for finding in sorted_findings:
        severity = finding.get("severity", "info")
        title = finding.get("title", "")

        if severity in ("critical", "high"):
            quick_wins.append({
                "action": title,
                "impact": f"Fixes {severity} issue",
                "severity": severity,
            })
        elif severity == "medium":
            medium_term.append({
                "action": title,
                "impact": "Improves GEO readiness",
                "severity": severity,
            })
        else:
            strategic.append({
                "action": title,
                "impact": "Long-term optimization",
                "severity": severity,
            })

    # Add score-based recommendations
    if scores.get("ai_citability", 0) < 50:
        medium_term.append({
            "action": "Optimize content blocks for AI citability (134-167 word self-contained passages)",
            "impact": "Could improve AI Citability score by 20-30 points",
        })

    if scores.get("schema", 0) < 40:
        quick_wins.append({
            "action": "Implement comprehensive structured data (schema.org)",
            "impact": "Could improve Schema score by 30-50 points",
        })

    if scores.get("brand_authority", 0) < 50:
        strategic.append({
            "action": "Build Wikipedia/Wikidata entity presence",
            "impact": "Strengthens brand authority for AI citation",
        })

    return {
        "quick_wins": quick_wins[:7],
        "medium_term": medium_term[:7],
        "strategic": strategic[:5],
    }
