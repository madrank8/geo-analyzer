"""
Business type auto-detection.
Merged from EntityOS scan_engine.detect_entity_type + geo-seo-claude patterns.
"""
import json
import re

ENTITY_TYPES = {
    "local_business":  "Physical local business with a geographic service area",
    "national_brand":  "National/international brand operating across regions",
    "digital_service": "Online-only service, SaaS, or digital product",
    "informational":   "Content/informational site, blog, publication, or resource",
    "ecommerce":       "E-commerce store selling products online",
    "agency":          "Service agency (marketing, design, consulting)",
}


def detect_business_type(html: str, text: str, url: str, structured_data: list = None) -> dict:
    """
    Auto-detect the business/entity type from page signals.

    Returns:
        {"type": str, "confidence": int, "signals": list, "description": str}
    """
    scores = {t: 0 for t in ENTITY_TYPES}
    signals = []
    text_lower = text.lower() if text else ""
    html_lower = html.lower() if html else ""

    # ── Signal 1: Physical address / NAP indicators ──
    phone_pattern = re.findall(r'(?:tel:|href=["\']tel:)([^"\'>]+)', html, re.I)
    has_address = bool(re.search(
        r'(?:street|road|avenue|blvd|drive|lane|suite|floor|level)\s+\d|'
        r'\d+\s+(?:street|road|avenue|blvd|drive|lane|floor)', text_lower
    ))
    has_map_embed = bool(re.search(r'google\.com/maps|maps\.googleapis|mapbox|leaflet', html_lower))
    has_opening_hours = bool(re.search(
        r'(?:open|hour|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*[-:]\s*\d', text_lower
    ))

    if phone_pattern:
        scores["local_business"] += 20
        signals.append(f"Phone number found: {phone_pattern[0][:15]}")
    if has_address:
        scores["local_business"] += 25
        signals.append("Physical address detected")
    if has_map_embed:
        scores["local_business"] += 20
        signals.append("Map embed found")
    if has_opening_hours:
        scores["local_business"] += 15
        signals.append("Opening hours detected")

    # ── Signal 2: Schema markup type ──
    schema_types = set()
    sd_list = structured_data or []
    for sd in sd_list:
        if isinstance(sd, dict):
            t = sd.get("@type", "")
            if isinstance(t, list):
                schema_types.update(t)
            else:
                schema_types.add(t)
        elif isinstance(sd, list):
            for item in sd:
                if isinstance(item, dict):
                    schema_types.add(item.get("@type", ""))

    # Also parse from HTML in case structured_data wasn't provided
    if not schema_types:
        schema_blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.I | re.DOTALL
        )
        for block in schema_blocks:
            try:
                schema = json.loads(block)
                if isinstance(schema, dict):
                    schema_types.add(schema.get("@type", ""))
                elif isinstance(schema, list):
                    for s in schema:
                        if isinstance(s, dict):
                            schema_types.add(s.get("@type", ""))
            except (json.JSONDecodeError, AttributeError):
                pass

    local_schema_types = {"LocalBusiness", "Restaurant", "Store", "MedicalBusiness",
                          "LegalService", "FinancialService", "RealEstateAgent",
                          "AutoDealer", "Dentist", "Plumber", "Electrician"}
    if schema_types & local_schema_types:
        scores["local_business"] += 30
        signals.append(f"Local schema: {', '.join(schema_types & local_schema_types)}")

    if "SoftwareApplication" in schema_types or "WebApplication" in schema_types:
        scores["digital_service"] += 30
        signals.append("Software/WebApp schema detected")

    if "Article" in schema_types or "BlogPosting" in schema_types or "NewsArticle" in schema_types:
        scores["informational"] += 25
        signals.append("Article/Blog schema detected")

    if "Product" in schema_types:
        scores["ecommerce"] += 25
        signals.append("Product schema detected")

    if "Organization" in schema_types and not (schema_types & local_schema_types):
        scores["national_brand"] += 15
        signals.append("Organization schema (non-local)")

    # ── Signal 3: Content keywords ──
    keyword_groups = {
        "local_business": [
            "near me", "service area", "serving", "located in", "our location",
            "local", "community", "free estimate", "call us", "book an appointment",
        ],
        "digital_service": [
            "saas", "software", "platform", "app", "dashboard", "api",
            "cloud", "subscription", "sign up", "free trial", "login",
            "pricing plan", "enterprise", "integration",
        ],
        "informational": [
            "blog", "article", "guide", "tutorial", "how to", "learn",
            "research", "study", "report", "news", "subscribe to newsletter",
        ],
        "national_brand": [
            "nationwide", "global", "international", "worldwide", "offices in",
            "headquarters", "franchise", "annual report", "investor",
        ],
        "ecommerce": [
            "add to cart", "checkout", "shipping", "free delivery", "shop now",
            "buy now", "product", "catalog", "wishlist", "out of stock",
        ],
        "agency": [
            "our services", "our team", "case study", "portfolio", "clients",
            "consultation", "strategy", "we help", "our approach",
        ],
    }

    for btype, keywords in keyword_groups.items():
        for kw in keywords:
            if kw in text_lower:
                scores[btype] += 3

    # ── Signal 4: URL patterns ──
    domain = url.split("/")[2] if "/" in url and len(url.split("/")) > 2 else ""
    local_tlds = [".nz", ".au", ".uk", ".ca", ".de", ".fr", ".nl", ".ie", ".za"]
    if any(domain.endswith(tld) for tld in local_tlds):
        scores["local_business"] += 10
        signals.append(f"Country-code TLD: {domain.split('.')[-1]}")

    if any(k in domain for k in ["app.", "saas", "cloud", "platform", "tool"]):
        scores["digital_service"] += 10
        signals.append("SaaS-like domain pattern")

    if any(k in domain for k in ["blog", "news", "wiki", "edu", "learn", "guide"]):
        scores["informational"] += 10
        signals.append("Informational domain pattern")

    if any(k in domain for k in ["shop", "store", "buy", "market"]):
        scores["ecommerce"] += 10
        signals.append("E-commerce domain pattern")

    # ── Determine winner ──
    max_type = max(scores, key=scores.get)
    max_score = scores[max_type]
    total = sum(scores.values()) or 1
    confidence = min(95, int((max_score / total) * 100))

    if max_score == 0:
        max_type = "informational"
        confidence = 30
        signals.append("No strong type signals — defaulting to informational")

    return {
        "type": max_type,
        "confidence": confidence,
        "signals": signals,
        "description": ENTITY_TYPES[max_type],
        "type_scores": scores,
    }
