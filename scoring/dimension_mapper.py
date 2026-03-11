"""
Dimension Mapper — Maps EntityOS 16 content dimensions to GEO 6 categories.
Bridge between EntityOS content engine and GEO scoring framework.
"""

# EntityOS dimension weights (sum to 1.0)
ENTITYOS_DIMENSIONS = {
    "entity_grounding":        {"weight": 0.10, "geo_category": "brand_authority"},
    "trust_architecture":      {"weight": 0.05, "geo_category": "brand_authority"},
    "eeat_depth":              {"weight": 0.10, "geo_category": "content_eeat"},
    "content_originality":     {"weight": 0.08, "geo_category": "content_eeat"},
    "nlp_clarity":             {"weight": 0.07, "geo_category": "content_eeat"},
    "entropic_density":        {"weight": 0.08, "geo_category": "content_eeat"},
    "passage_ranking":         {"weight": 0.07, "geo_category": "ai_citability"},
    "semantic_depth":          {"weight": 0.08, "geo_category": "ai_citability"},
    "intent_alignment":        {"weight": 0.07, "geo_category": "platform_optimization"},
    "structural_optimization": {"weight": 0.04, "geo_category": "technical"},
    "readability":             {"weight": 0.03, "geo_category": "technical"},
    "freshness":               {"weight": 0.05, "geo_category": "technical"},
    "lexical_diversity":       {"weight": 0.05, "geo_category": "content_eeat"},
    "syntactic_burstiness":    {"weight": 0.05, "geo_category": "content_eeat"},
    "emotional_variance":      {"weight": 0.04, "geo_category": "content_eeat"},
    "semantic_drift":          {"weight": 0.04, "geo_category": "content_eeat"},
}


def map_dimensions_to_geo(dimension_scores: dict) -> dict:
    """
    Map EntityOS dimension scores to GEO category contributions.

    Args:
        dimension_scores: {"dimension_name": {"score": 0-100, ...}, ...}

    Returns:
        {"ai_citability": float, "brand_authority": float, "content_eeat": float,
         "technical": float, "platform_optimization": float}
    """
    geo_contributions = {
        "ai_citability": [],
        "brand_authority": [],
        "content_eeat": [],
        "technical": [],
        "platform_optimization": [],
    }

    for dim_name, dim_meta in ENTITYOS_DIMENSIONS.items():
        if dim_name in dimension_scores:
            dim_data = dimension_scores[dim_name]
            score = dim_data.get("score", 50) if isinstance(dim_data, dict) else dim_data
            category = dim_meta["geo_category"]
            weight = dim_meta["weight"]
            geo_contributions[category].append({"score": score, "weight": weight})

    # Weighted average per category
    result = {}
    for category, items in geo_contributions.items():
        if items:
            total_weight = sum(i["weight"] for i in items)
            if total_weight > 0:
                weighted_sum = sum(i["score"] * i["weight"] for i in items)
                result[category] = round(weighted_sum / total_weight, 1)
            else:
                result[category] = 0
        else:
            result[category] = None  # No dimension data available

    return result


def blend_scores(deterministic_scores: dict, gemini_scores: dict,
                 gemini_weight: float = 0.4) -> dict:
    """
    Blend deterministic analyzer scores with Gemini dimension-mapped scores.

    Args:
        deterministic_scores: From the 5 analyzers (always available)
        gemini_scores: From dimension_mapper (only when Gemini API is available)
        gemini_weight: How much to weight Gemini scores (0.0 to 1.0)

    Returns:
        Blended scores dict
    """
    blended = {}
    det_weight = 1.0 - gemini_weight

    for category in deterministic_scores:
        det_score = deterministic_scores.get(category, 0)
        gem_score = gemini_scores.get(category)

        if gem_score is not None:
            blended[category] = round(det_score * det_weight + gem_score * gemini_weight)
        else:
            blended[category] = det_score

    return blended
