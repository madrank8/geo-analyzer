"""
SEER Veto Engine — Binary Trust Classifiers for EntityOS.

Hard vetoes that override positive classifier scores.
Modeled after Google's spam classifiers: a single triggered veto
can override otherwise positive quality signals.

Each veto returns:
  - triggered: bool
  - severity: "critical" | "high" | "medium" | "warning"
  - evidence: str (what triggered it)
  - recommendation: str (how to fix)

v2.0 — A/B Test Accuracy Sprint:
  - Fixed privacy detection: checks footer, nav, common URL paths, meta tags
  - Entity scan awareness: skips URL-dependent vetoes on entity scans
  - Content-publisher exception for NAP checks (multi-entity sites)
  - Smarter affiliate/lead-gen threshold (word count normalization)
  - Thin content veto: higher threshold, JS rendering awareness
  - New "warning" severity tier for borderline signals (flags but doesn't block cert)
"""

import re
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse


# ════════════════════════════════════════════════════════════════════════
#  KNOWN CONTENT PUBLISHERS / AGGREGATORS
#  These legitimately have multiple entity names in their schema.
# ════════════════════════════════════════════════════════════════════════

KNOWN_PUBLISHERS = {
    "webmd.com", "healthline.com", "mayoclinic.org", "medicalnewstoday.com",
    "verywellhealth.com", "clevelandclinic.org",
    "backlinko.com", "neilpatel.com", "semrush.com", "ahrefs.com", "moz.com",
    "searchengineland.com", "searchenginejournal.com",
    "forbes.com", "businessinsider.com", "entrepreneur.com", "inc.com",
    "techcrunch.com", "theverge.com", "wired.com", "cnet.com",
    "nytimes.com", "washingtonpost.com", "bbc.com", "cnn.com", "reuters.com",
    "wikipedia.org", "wikimedia.org",
    "amazon.com", "ebay.com", "walmart.com", "target.com",
    "yelp.com", "tripadvisor.com", "glassdoor.com",
    "reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com",
    "medium.com", "substack.com",
    "hubspot.com", "shopify.com", "squarespace.com",
}


def _extract_domain(url: str) -> str:
    """Extract bare domain from a URL string (e.g., 'www.webmd.com' -> 'webmd.com')."""
    if not url:
        return ""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        # Strip www.
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""


def _is_known_publisher(url: str) -> bool:
    """Check if the URL belongs to a known content publisher/aggregator."""
    domain = _extract_domain(url)
    if not domain:
        return False
    # Check exact match and parent domain
    for pub in KNOWN_PUBLISHERS:
        if domain == pub or domain.endswith("." + pub):
            return True
    return False


# ════════════════════════════════════════════════════════════════════════
#  VETO DEFINITIONS
# ════════════════════════════════════════════════════════════════════════

def veto_content_decay(html: str, text: str, html_signals: dict, **kw) -> dict:
    """Manipulative date freshness — future-dating, stale content with fresh dates."""
    evidence = []
    current_year = datetime.now().year

    # Check for future years in copyright/dates
    future_years = re.findall(r'(?:©|\bcopyright\b|\bCopyright\b)\s*(\d{4})', html)
    for y in future_years:
        yr = int(y)
        if yr > current_year:
            evidence.append(f"Future copyright year: {yr} (current: {current_year})")

    # Check for date manipulation patterns in meta/structured data
    date_patterns = re.findall(
        r'(?:datePublished|dateModified|article:published_time|article:modified_time)["\'"]?\s*[:=]\s*["\']?(\d{4})',
        html, re.I
    )
    for y in date_patterns:
        yr = int(y)
        if yr > current_year:
            evidence.append(f"Future structured data date: {yr}")

    # Check for "Updated 2026" type freshness manipulation
    fresh_claims = re.findall(r'(?:updated|modified|revised)\s+(?:on\s+)?(?:in\s+)?(\d{4})', text, re.I)
    for y in fresh_claims:
        yr = int(y)
        if yr > current_year:
            evidence.append(f"Claims future update year: {yr}")

    # Check for copyright range ending in future
    range_years = re.findall(r'©\s*\d{4}\s*[-–]\s*(\d{4})', html)
    for y in range_years:
        yr = int(y)
        if yr > current_year + 1:
            evidence.append(f"Copyright range extends to {yr}")

    return {
        "id": "content_decay",
        "name": "Content Decay / Date Manipulation",
        "triggered": len(evidence) > 0,
        "severity": "critical",
        "evidence": "; ".join(evidence) if evidence else "No date manipulation detected",
        "recommendation": "Use current or dynamic year in copyright. Ensure structured data dates reflect actual publish/update dates."
    }


def veto_missing_privacy_terms(html: str, html_signals: dict, scan_context: dict = None, **kw) -> dict:
    """Missing legal pages — no privacy policy, terms of service, or legal disclosure.

    v2.0: Enhanced detection — checks footer, nav, common URL paths, link text,
    and meta references. Skipped entirely on entity scans (no URL to check).
    """
    # Skip on entity scans — there's no page to check for privacy links
    ctx = scan_context or {}
    if ctx.get("is_entity_scan"):
        return {
            "id": "missing_privacy_terms",
            "name": "Missing Privacy & Legal Terms",
            "triggered": False,
            "severity": "high",
            "evidence": "Skipped — entity scan (no URL-based page to check)",
            "recommendation": ""
        }

    evidence = []
    html_lower = html.lower()

    # ── Privacy Policy Detection ──
    # Method 1: href containing privacy-related paths
    has_privacy = bool(re.search(
        r'href\s*=\s*["\'][^"\']*(?:/privacy|/datenschutz|/privacidad|privacy-policy|privacy_policy|data-protection)[^"\']*["\']',
        html_lower
    ))
    # Method 2: Link text containing "privacy"
    if not has_privacy:
        has_privacy = bool(re.search(
            r'<a[^>]*>[^<]*(?:privacy\s*policy|privacy\s*notice|datenschutz|privacidad)[^<]*</a>',
            html_lower
        ))
    # Method 3: Footer/nav region containing privacy reference
    if not has_privacy:
        footer_match = re.search(r'<footer[^>]*>(.*?)</footer>', html_lower, re.DOTALL)
        if footer_match:
            footer = footer_match.group(1)
            has_privacy = bool(re.search(r'privacy', footer))
    # Method 4: Meta/link tags referencing privacy
    if not has_privacy:
        has_privacy = bool(re.search(
            r'(?:privacy|p13n|gdpr|ccpa|data.protection)',
            re.sub(r'<script.*?</script>', '', html_lower, flags=re.DOTALL)[:5000]  # Check head area
        ))

    # ── Terms of Service Detection ──
    has_terms = bool(re.search(
        r'href\s*=\s*["\'][^"\']*(?:/terms|/tos|/conditions|/nutzungsbedingungen|terms-of-service|terms-of-use|terms_of_service)[^"\']*["\']',
        html_lower
    ))
    if not has_terms:
        has_terms = bool(re.search(
            r'<a[^>]*>[^<]*(?:terms\s*(?:of\s*(?:service|use))?|conditions|nutzungsbedingungen)[^<]*</a>',
            html_lower
        ))
    if not has_terms:
        footer_match = re.search(r'<footer[^>]*>(.*?)</footer>', html_lower, re.DOTALL)
        if footer_match:
            footer = footer_match.group(1)
            has_terms = bool(re.search(r'terms', footer))

    # ── Legal/Disclaimer Detection ──
    has_legal = bool(re.search(
        r'href\s*=\s*["\'][^"\']*(?:/legal|/disclaimer|/impressum|/imprint)[^"\']*["\']',
        html_lower
    ))
    if not has_legal:
        has_legal = bool(re.search(
            r'<a[^>]*>[^<]*(?:legal|disclaimer|impressum|imprint)[^<]*</a>',
            html_lower
        ))

    if not has_privacy:
        evidence.append("No privacy policy link found")
    if not has_terms:
        evidence.append("No terms of service link found")

    # Only trigger if BOTH privacy AND terms are missing AND no legal page
    triggered = not has_privacy and not has_terms and not has_legal

    return {
        "id": "missing_privacy_terms",
        "name": "Missing Privacy & Legal Terms",
        "triggered": triggered,
        "severity": "high",
        "evidence": "; ".join(evidence) if evidence else "Legal pages linked",
        "recommendation": "Add visible links to Privacy Policy and Terms of Service in footer. Required for YMYL and ad-supported sites."
    }


def veto_fake_expert_personas(html: str, text: str, **kw) -> dict:
    """Unverifiable authors — generic 'our team' or unnamed experts."""
    evidence = []

    # Check for author attribution
    has_author = bool(re.search(
        r'(?:author|byline|written.by|reviewed.by|medically.reviewed)[":\s]+[A-Z][a-z]+\s+[A-Z][a-z]+',
        html
    ))

    # Patterns that suggest fake/generic expertise
    fake_patterns = [
        (r'(?:our|the)\s+(?:team|staff|experts?|specialists?|professionals?)\s+(?:of|will|can|has|have)',
         "Generic 'our team/experts' without named individuals"),
        (r'licensed\s+(?:doctors?|physicians?|professionals?|experts?)\s+(?:will|can|review|oversee)',
         "Claims 'licensed doctors' without naming them"),
        (r'(?:board.certified|certified)\s+(?:doctors?|physicians?|professionals?)\s+(?:are|will)',
         "Claims board certification without specific names"),
    ]

    for pattern, desc in fake_patterns:
        if re.search(pattern, text, re.I):
            if not has_author:
                evidence.append(desc)

    # Check for schema author
    has_schema_author = bool(re.search(
        r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"[A-Z]', html
    ))

    triggered = len(evidence) > 0 and not has_schema_author

    # Downgrade to warning if only one weak signal
    severity = "warning" if len(evidence) == 1 else "high"

    return {
        "id": "fake_expert_personas",
        "name": "Unverifiable Expert Personas",
        "triggered": triggered,
        "severity": severity,
        "evidence": "; ".join(evidence) if evidence else "Named authors found",
        "recommendation": "Name specific authors with verifiable credentials. Add author schema markup with name, credentials, and links to professional profiles."
    }


def veto_broken_entity_trust(html: str, text: str, html_signals: dict,
                              scan_context: dict = None, **kw) -> dict:
    """NAP inconsistency — conflicting business names, addresses, or phone numbers.

    v2.0: Content-publisher exception — multi-entity schema is normal for
    publishers, aggregators, and large content sites.
    """
    evidence = []
    ctx = scan_context or {}
    url = ctx.get("url", "")

    # Extract phone numbers
    phones = re.findall(r'(?:\+1[-.\\s]?)?(?:\(?\d{3}\)?[-.\\s]?)?\d{3}[-.\\s]?\d{4}', text)
    phones = list(set(phones))
    if len(phones) > 3:
        evidence.append(f"Multiple phone numbers detected ({len(phones)}) — possible NAP inconsistency")

    # Check for conflicting addresses
    addresses = re.findall(
        r'\d+\s+[A-Z][a-z]+\s+(?:St|Ave|Blvd|Rd|Dr|Ln|Way|Ct|Pl|Circle)',
        text
    )
    addresses = list(set(addresses))
    if len(addresses) > 2:
        evidence.append(f"Multiple distinct addresses found ({len(addresses)})")

    # Check for schema with mismatched data
    schema_names = re.findall(r'"name"\s*:\s*"([^"]+)"', html)
    unique_names = list(set(n.lower().strip() for n in schema_names if len(n) > 3))

    if len(unique_names) > 3:
        # Content-publisher exception: if this is a known publisher or has
        # publisher signals, multiple entity names in schema is expected
        is_publisher = _is_known_publisher(url)

        # Also detect publisher patterns: article schema, multiple author names,
        # news/blog indicators
        has_article_schema = bool(re.search(r'"@type"\s*:\s*"(?:Article|NewsArticle|BlogPosting)"', html))
        has_publisher_schema = bool(re.search(r'"@type"\s*:\s*"(?:Organization|NewsMediaOrganization)"', html))
        publisher_signals = is_publisher or has_article_schema or has_publisher_schema

        if publisher_signals:
            # Downgrade to informational warning, not a veto
            return {
                "id": "broken_entity_trust",
                "name": "Broken Entity Trust (NAP Inconsistency)",
                "triggered": False,
                "severity": "high",
                "evidence": f"Content publisher detected — {len(unique_names)} entity names in schema is normal for publishers/aggregators",
                "recommendation": ""
            }
        else:
            evidence.append(f"Multiple entity names in schema ({len(unique_names)} distinct names)")

    return {
        "id": "broken_entity_trust",
        "name": "Broken Entity Trust (NAP Inconsistency)",
        "triggered": len(evidence) > 0,
        "severity": "high",
        "evidence": "; ".join(evidence) if evidence else "Entity data appears consistent",
        "recommendation": "Ensure consistent Name, Address, Phone across all pages and schema markup. One canonical business identity per domain."
    }


def veto_content_scraping(text: str, html: str, **kw) -> dict:
    """Content scraping traces — duplicate boilerplate, attribution stripping."""
    evidence = []

    # Check for common scraping artifacts
    scrape_patterns = [
        (r'(?:source|via|originally.published|originally.posted)\s*:\s*(?:http|www)', "Contains source attribution suggesting copied content"),
        (r'(?:image.credit|photo.credit|image.source)\s*:\s*(?:shutterstock|getty|istock|adobe.stock|unsplash)', "Stock image attributions suggest aggregated content"),
    ]

    for pattern, desc in scrape_patterns:
        if re.search(pattern, text, re.I):
            evidence.append(desc)

    # Extremely high paragraph repetition
    paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 50]
    if paragraphs:
        para_counts = Counter(paragraphs)
        duplicates = [(p[:60], c) for p, c in para_counts.items() if c > 2]
        if duplicates:
            evidence.append(f"Repeated paragraph blocks: {len(duplicates)} paragraphs appear 3+ times")

    return {
        "id": "content_scraping_traces",
        "name": "Content Scraping / Duplication Traces",
        "triggered": len(evidence) > 0,
        "severity": "critical",
        "evidence": "; ".join(evidence) if evidence else "No scraping indicators detected",
        "recommendation": "Create original content. If curating, add substantial original analysis. Remove duplicate content blocks."
    }


def veto_excessive_cta(html: str, text: str, html_signals: dict, **kw) -> dict:
    """Excessive CTA saturation — aggressive conversion-focused page."""
    evidence = []

    # Count CTA-like elements
    cta_patterns = [
        r'(?:buy\s+now|order\s+now|sign\s+up|subscribe|get\s+started|claim|grab|hurry|limited\s+time|act\s+now|don.t\s+miss)',
        r'(?:add\s+to\s+cart|checkout|purchase|enroll|register\s+now|book\s+now|schedule\s+now)',
    ]
    cta_count = 0
    for pattern in cta_patterns:
        cta_count += len(re.findall(pattern, text, re.I))

    # Count button/CTA elements in HTML
    btn_count = len(re.findall(r'class=["\'][^"\']*(?:cta|btn-primary|buy-btn|order-btn)[^"\']*["\']', html, re.I))
    btn_count += len(re.findall(r'<button[^>]*>.*?(?:buy|order|subscribe|sign.up).*?</button>', html, re.I))

    total_ctas = cta_count + btn_count
    word_count = len(text.split())

    if word_count > 0:
        cta_ratio = total_ctas / (word_count / 100)  # CTAs per 100 words
        if cta_ratio > 3:
            evidence.append(f"Extremely high CTA density: {total_ctas} CTAs in {word_count} words ({cta_ratio:.1f} per 100 words)")
        elif cta_ratio > 2:
            evidence.append(f"High CTA density: {total_ctas} CTAs in {word_count} words ({cta_ratio:.1f} per 100 words)")

    # Urgency/scarcity manipulation
    urgency_count = len(re.findall(
        r'(?:limited\s+time|only\s+\d+\s+left|hurry|expires?\s+(?:soon|today)|countdown|last\s+chance|final\s+offer)',
        text, re.I
    ))
    if urgency_count >= 3:
        evidence.append(f"Heavy urgency/scarcity tactics: {urgency_count} instances")

    return {
        "id": "excessive_cta_saturation",
        "name": "Excessive CTA / Sales Saturation",
        "triggered": len(evidence) > 0,
        "severity": "medium",
        "evidence": "; ".join(evidence) if evidence else "CTA density within normal range",
        "recommendation": "Reduce aggressive CTAs. Focus on content value first. Limit urgency/scarcity language to genuine offers."
    }


def veto_keyword_cannibalization(html: str, text: str, html_signals: dict, **kw) -> dict:
    """Self-competing pages — detected via title/h1 patterns suggesting cannibalization."""
    evidence = []

    title = html_signals.get("title", "")
    h1s = html_signals.get("h1_texts", [])

    # Multiple H1 tags (structural issue)
    if len(h1s) > 1:
        evidence.append(f"Multiple H1 tags ({len(h1s)}): {', '.join(h[:40] for h in h1s[:3])}")

    # Title and H1 significantly different (targeting different queries)
    if title and h1s:
        title_words = set(title.lower().split())
        h1_words = set(h1s[0].lower().split())
        overlap = title_words & h1_words
        if len(overlap) < 2 and len(title_words) > 3 and len(h1_words) > 3:
            evidence.append(f"Title and H1 target different topics: '{title[:40]}' vs '{h1s[0][:40]}'")

    return {
        "id": "keyword_cannibalization",
        "name": "Keyword Cannibalization Signals",
        "triggered": len(evidence) > 0,
        "severity": "medium",
        "evidence": "; ".join(evidence) if evidence else "Title/H1 alignment OK",
        "recommendation": "Ensure each page targets one clear topic. Title tag and H1 should be aligned. Consolidate pages targeting the same query."
    }


def veto_thin_city_pages(html: str, text: str, html_signals: dict,
                          scan_context: dict = None, **kw) -> dict:
    """Doorway/thin city pages — template content with city name swapped.

    v2.0: Raised thin-content threshold from 200 to 300 words.
    JS-rendered pages get a pass if the HTML shell is clearly a SPA wrapper.
    """
    evidence = []
    text_lower = text.lower()
    word_count = len(text.split())

    # Check for JS rendering failure indicators
    is_js_shell = bool(re.search(
        r'(?:id\s*=\s*["\'](?:root|app|__next|__nuxt)["\']|'
        r'noscript.*?enable\s+javascript|'
        r'<div\s+id=["\']app["\']>\s*</div>)',
        html, re.I
    ))

    # If this looks like a JS shell, don't flag thin content — it's a rendering failure, not thin content
    if is_js_shell and word_count < 500:
        return {
            "id": "thin_city_pages",
            "name": "Thin / Doorway City Pages",
            "triggered": False,
            "severity": "critical",
            "evidence": f"JS-rendered page detected (only {word_count} words extracted) — thin content check skipped; content likely behind JS rendering",
            "recommendation": ""
        }

    # Very short page — raised threshold from 200 to 300
    if word_count < 300:
        evidence.append(f"Very thin content: only {word_count} words")

    # City name stuffing pattern
    city_patterns = re.findall(
        r'(?:in|near|serving|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s*[A-Z]{2})?)',
        text
    )
    if len(city_patterns) > 5:
        evidence.append(f"Excessive city/location mentions: {len(city_patterns)} location references")

    # Template detection: very similar paragraph structures
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 20]
    if len(sentences) > 5:
        stripped = [re.sub(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:,\s*[A-Z]{2})?', 'CITY', s) for s in sentences]
        template_count = Counter(stripped)
        repeated_templates = [(t[:50], c) for t, c in template_count.items() if c > 2]
        if repeated_templates:
            evidence.append(f"Template-like content: {len(repeated_templates)} repeated sentence patterns")

    return {
        "id": "thin_city_pages",
        "name": "Thin / Doorway City Pages",
        "triggered": len(evidence) >= 2,  # Need 2+ signals
        "severity": "critical",
        "evidence": "; ".join(evidence) if evidence else "Content appears unique",
        "recommendation": "Create unique, substantive content for each location. Include local landmarks, specific service details, and genuine local expertise."
    }


def veto_auto_generated_faq(html: str, text: str, **kw) -> dict:
    """Low-quality auto-generated FAQ schema."""
    evidence = []

    has_faq_schema = bool(re.search(r'"@type"\s*:\s*"FAQPage"', html))

    if has_faq_schema:
        answers = re.findall(r'"acceptedAnswer"\s*:\s*\{[^}]*"text"\s*:\s*"([^"]+)"', html)

        if answers:
            short_answers = [a for a in answers if len(a.split()) < 15]
            if len(short_answers) > len(answers) / 2:
                evidence.append(f"FAQ schema with thin answers: {len(short_answers)}/{len(answers)} answers under 15 words")

            answer_starts = [a[:30].lower() for a in answers]
            start_counts = Counter(answer_starts)
            repeated = [s for s, c in start_counts.items() if c > 2]
            if repeated:
                evidence.append(f"FAQ answers follow repetitive template pattern")

    return {
        "id": "auto_generated_faq",
        "name": "Auto-Generated FAQ Schema",
        "triggered": len(evidence) > 0,
        "severity": "medium",
        "evidence": "; ".join(evidence) if evidence else "FAQ schema quality OK or not present",
        "recommendation": "Write substantive FAQ answers (50+ words each). Each answer should provide unique value, not templated responses."
    }


def veto_obfuscated_pricing(html: str, text: str, **kw) -> dict:
    """Hidden or misleading pricing — prices buried, bait-and-switch patterns."""
    evidence = []
    text_lower = text.lower()

    is_commercial = bool(re.search(
        r'(?:pricing|price|cost|plan|subscription|package|tier|starting.at|\$|per.month|/mo)',
        text_lower
    ))

    if is_commercial:
        contact_for_price = bool(re.search(
            r'(?:contact\s+(?:us|sales)\s+for\s+pric|request\s+(?:a\s+)?quote|call\s+for\s+(?:a\s+)?price|custom\s+pricing)',
            text_lower
        ))
        has_actual_prices = bool(re.search(r'\$\d+|\d+(?:\.\d{2})?\s*(?:/mo|per\s+month|/year)', text))

        if contact_for_price and not has_actual_prices:
            evidence.append("Pricing page exists but all prices hidden behind contact forms")

        asterisk_count = text.count('*')
        if asterisk_count > 5:
            evidence.append(f"Heavy fine-print indicators ({asterisk_count} asterisks)")

    return {
        "id": "obfuscated_pricing",
        "name": "Obfuscated / Hidden Pricing",
        "triggered": len(evidence) > 0,
        "severity": "medium",
        "evidence": "; ".join(evidence) if evidence else "Pricing transparency OK or non-commercial page",
        "recommendation": "Display clear pricing. If custom pricing is necessary, show starting prices or ranges. Minimize fine-print disclaimers."
    }


def veto_lead_gen_front(html: str, text: str, html_signals: dict,
                         scan_context: dict = None, **kw) -> dict:
    """Disguised lead-gen / affiliate page masquerading as informational content.

    v2.0: Smarter threshold — normalizes affiliate count by word count.
    Legitimate content sites with some affiliate links (backlinko, webmd)
    are no longer flagged. Only fires when the page is primarily affiliate-driven.
    """
    evidence = []
    ctx = scan_context or {}
    url = ctx.get("url", "")
    word_count = len(text.split())

    # High form density relative to content
    form_count = len(re.findall(r'<form', html, re.I))
    if form_count >= 3 and word_count < 500:
        evidence.append(f"High form-to-content ratio: {form_count} forms in {word_count} words")

    # Affiliate link patterns
    aff_patterns = [
        r'(?:ref=|affiliate|partner.?id|click.?id|tracking|subid|hoplink)',
        r'(?:shareasale|clickbank|cj\.com|impact\.com|partnerize)',
    ]
    aff_count = 0
    for pattern in aff_patterns:
        aff_count += len(re.findall(pattern, html, re.I))

    # ── v2.0: Normalize by word count ──
    # A 3000-word article with 20 affiliate links = 0.67 per 100 words (normal for content sites)
    # A 200-word page with 20 affiliate links = 10.0 per 100 words (likely pure affiliate page)
    if word_count > 0 and aff_count > 0:
        aff_per_100_words = aff_count / (word_count / 100)

        # Known publisher exception: skip affiliate check entirely
        if _is_known_publisher(url):
            pass  # Don't flag known publishers for affiliate links
        elif aff_per_100_words > 3.0:
            # Very high ratio: clearly affiliate-driven
            evidence.append(
                f"Extremely high affiliate density: {aff_count} affiliate/tracking links "
                f"in {word_count} words ({aff_per_100_words:.1f} per 100 words)"
            )
        elif aff_per_100_words > 1.5 and word_count < 800:
            # High ratio on short content = likely affiliate page
            evidence.append(
                f"Thin content with heavy affiliate links: {aff_count} links "
                f"in {word_count} words ({aff_per_100_words:.1f} per 100 words)"
            )
    elif aff_count > 20 and word_count < 300:
        # Absolute threshold for very thin pages
        evidence.append(f"Heavy affiliate/tracking links on thin page: {aff_count} instances in {word_count} words")

    # "Best X" listicle with all affiliate links — only flag if density is also high
    is_listicle = bool(re.search(r'(?:best|top|review)', html_signals.get("title", ""), re.I))
    if is_listicle and aff_count > 10 and word_count < 500:
        evidence.append("Thin affiliate listicle: 'Best/Top' title with dense affiliate links on short page")

    # Determine severity based on strength of signal
    severity = "high"
    if len(evidence) == 1 and "Thin content" not in evidence[0]:
        severity = "warning"  # Borderline — flag but don't block cert

    return {
        "id": "lead_gen_front",
        "name": "Disguised Lead-Gen / Affiliate Front",
        "triggered": len(evidence) > 0,
        "severity": severity,
        "evidence": "; ".join(evidence) if evidence else "No lead-gen front pattern detected",
        "recommendation": "Ensure content provides genuine value beyond lead collection. Disclose affiliate relationships. Balance forms with substantive content."
    }


def veto_review_velocity_anomaly(text: str, html: str, **kw) -> dict:
    """Suspicious review patterns — fake review velocity or patterns."""
    evidence = []

    review_schema = re.findall(r'"@type"\s*:\s*"Review"', html)
    rating_schema = re.findall(r'"ratingValue"\s*:\s*"?(\d+(?:\.\d+)?)"?', html)

    if rating_schema:
        ratings = [float(r) for r in rating_schema]
        perfect = [r for r in ratings if r >= 4.9]
        if len(perfect) == len(ratings) and len(ratings) >= 3:
            evidence.append(f"All {len(ratings)} reviews are 4.9-5.0 stars — suspicious pattern")

        review_dates = re.findall(r'"datePublished"\s*:\s*"(\d{4}-\d{2})', html)
        if review_dates:
            date_counts = Counter(review_dates)
            spikes = [(d, c) for d, c in date_counts.items() if c > 3]
            if spikes:
                evidence.append(f"Review velocity spike: {spikes[0][1]} reviews in {spikes[0][0]}")

    return {
        "id": "review_velocity_anomaly",
        "name": "Review Velocity Anomaly",
        "triggered": len(evidence) > 0,
        "severity": "high",
        "evidence": "; ".join(evidence) if evidence else "Review patterns appear normal or no reviews present",
        "recommendation": "Encourage organic reviews over time. Avoid soliciting bulk reviews in short periods. Ensure review diversity (not all 5-star)."
    }


def veto_site_reputation_proximity(html: str, html_signals: dict, **kw) -> dict:
    """Toxic neighborhood — links to/from known spam, PBN, or low-quality domains."""
    evidence = []

    links = re.findall(r'href=["\']https?://([^/"\' ]+)', html)

    toxic_tld_patterns = ['.xyz', '.top', '.click', '.loan', '.work', '.gq', '.cf', '.tk', '.ml', '.ga']
    toxic_count = 0
    for link in links:
        for tld in toxic_tld_patterns:
            if link.endswith(tld):
                toxic_count += 1

    if toxic_count > 3:
        evidence.append(f"Links to {toxic_count} domains with spam-associated TLDs")

    hidden_links = re.findall(
        r'(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0)[^>]*<a\s+href',
        html, re.I
    )
    if hidden_links:
        evidence.append(f"Hidden links detected ({len(hidden_links)} instances)")

    return {
        "id": "site_reputation_proximity",
        "name": "Site Reputation / Toxic Proximity",
        "triggered": len(evidence) > 0,
        "severity": "critical",
        "evidence": "; ".join(evidence) if evidence else "No toxic proximity signals detected",
        "recommendation": "Audit outbound links. Remove links to spam/low-quality domains. Ensure no hidden links exist."
    }


# ════════════════════════════════════════════════════════════════════════
#  VETO RUNNER
# ════════════════════════════════════════════════════════════════════════

ALL_VETOES = [
    veto_content_decay,
    veto_missing_privacy_terms,
    veto_fake_expert_personas,
    veto_broken_entity_trust,
    veto_content_scraping,
    veto_excessive_cta,
    veto_keyword_cannibalization,
    veto_thin_city_pages,
    veto_auto_generated_faq,
    veto_obfuscated_pricing,
    veto_lead_gen_front,
    veto_review_velocity_anomaly,
    veto_site_reputation_proximity,
]


def run_vetoes(html: str, text: str, html_signals: dict, nlp_data: dict = None,
               text_stats: dict = None, scores: dict = None,
               scan_context: dict = None) -> dict:
    """
    Run all 13 veto classifiers and return results.

    Args:
        scan_context: Optional dict with scan metadata:
            - is_entity_scan: bool — True if running against entity pipeline data
            - url: str — the URL or entity query being scanned

    Returns:
        {
            "vetoes": [...],
            "triggered_vetoes": [...],
            "veto_count": int,
            "critical_count": int,
            "high_count": int,
            "medium_count": int,
            "warning_count": int,
            "certification_status": "CERTIFIED" | "NEEDS_REVIEW" | "NOT_CERTIFIED",
            "certification_reason": str,
        }
    """
    kwargs = {
        "html": html,
        "text": text,
        "html_signals": html_signals or {},
        "nlp_data": nlp_data or {},
        "text_stats": text_stats or {},
        "scores": scores or {},
        "scan_context": scan_context or {},
    }

    vetoes = []
    for veto_fn in ALL_VETOES:
        try:
            result = veto_fn(**kwargs)
            vetoes.append(result)
        except Exception as e:
            vetoes.append({
                "id": veto_fn.__name__.replace("veto_", ""),
                "name": veto_fn.__name__.replace("veto_", "").replace("_", " ").title(),
                "triggered": False,
                "severity": "medium",
                "evidence": f"Veto check error: {str(e)}",
                "recommendation": "",
            })

    triggered = [v for v in vetoes if v["triggered"]]
    critical_count = len([v for v in triggered if v["severity"] == "critical"])
    high_count = len([v for v in triggered if v["severity"] == "high"])
    medium_count = len([v for v in triggered if v["severity"] == "medium"])
    warning_count = len([v for v in triggered if v["severity"] == "warning"])

    # Certification logic — warnings don't block certification
    if critical_count > 0:
        status = "NOT_CERTIFIED"
        reason = f"{critical_count} critical veto(s) triggered: {', '.join(v['name'] for v in triggered if v['severity'] == 'critical')}"
    elif high_count > 0:
        status = "NEEDS_REVIEW"
        reason = f"{high_count} high-severity veto(s) triggered: {', '.join(v['name'] for v in triggered if v['severity'] == 'high')}"
    elif medium_count > 0:
        status = "NEEDS_REVIEW"
        reason = f"{medium_count} medium-severity issue(s) found"
    elif warning_count > 0:
        # Warnings alone don't block certification — page gets certified with notes
        status = "CERTIFIED"
        reason = f"All hard vetoes passed — {warning_count} advisory warning(s) noted: {', '.join(v['name'] for v in triggered if v['severity'] == 'warning')}"
    else:
        status = "CERTIFIED"
        reason = "All 13 veto checks passed — no trust-breaking signals detected"

    return {
        "vetoes": vetoes,
        "triggered_vetoes": triggered,
        "veto_count": len(triggered),
        "critical_count": critical_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "warning_count": warning_count,
        "certification_status": status,
        "certification_reason": reason,
    }
