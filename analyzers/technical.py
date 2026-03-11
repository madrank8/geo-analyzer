"""
Analyzer 3: Technical Foundations
SSR, security headers, HTTPS, meta tags, mobile, images.
"""
import re
from analyzers.base import AnalyzerBase


class TechnicalAnalyzer(AnalyzerBase):
    name = "technical"

    async def analyze(self, page_data: dict, business_type: str, api_keys: dict = None) -> dict:
        html = page_data.get("html", "")
        url = page_data.get("url", "")
        findings = []
        recommendations = []
        checks = {}

        # ── 1. HTTPS ──
        is_https = url.startswith("https://")
        checks["https"] = is_https
        if not is_https:
            findings.append({"severity": "critical", "title": "Not Using HTTPS",
                            "description": "Site is not served over HTTPS."})
            recommendations.append("Migrate to HTTPS with proper redirects")

        # ── 2. SSR ──
        has_ssr = page_data.get("has_ssr_content", True)
        checks["ssr"] = has_ssr
        if not has_ssr:
            findings.append({"severity": "high", "title": "No Server-Side Rendering",
                            "description": "Content is rendered client-side only, invisible to AI crawlers."})
            recommendations.append("Implement SSR or pre-rendering for public content pages")

        # ── 3. Security Headers ──
        sec_headers = page_data.get("security_headers", {})
        present_headers = [h for h, v in sec_headers.items() if v]
        missing_headers = [h for h, v in sec_headers.items() if not v]
        checks["security_headers"] = {
            "present": present_headers,
            "missing": missing_headers,
            "count": len(present_headers),
        }
        if len(missing_headers) > 3:
            findings.append({"severity": "medium", "title": "Missing Security Headers",
                            "description": f"Missing: {', '.join(missing_headers[:3])}"})
            recommendations.append("Add Strict-Transport-Security, Content-Security-Policy, and X-Content-Type-Options headers")

        # ── 4. Meta Tags ──
        meta = page_data.get("meta_tags", {})
        has_title = bool(page_data.get("title"))
        has_description = bool(page_data.get("description"))
        has_canonical = bool(page_data.get("canonical"))
        has_viewport = bool(meta.get("viewport"))
        has_og_title = bool(meta.get("og:title"))
        has_og_desc = bool(meta.get("og:description"))
        has_og_image = bool(meta.get("og:image"))
        has_twitter_card = bool(meta.get("twitter:card"))

        meta_score = sum([
            has_title * 15, has_description * 15, has_canonical * 10,
            has_viewport * 10, has_og_title * 10, has_og_desc * 10,
            has_og_image * 10, has_twitter_card * 10,
        ])

        checks["meta_tags"] = {
            "title": has_title, "description": has_description,
            "canonical": has_canonical, "viewport": has_viewport,
            "og_title": has_og_title, "og_description": has_og_desc,
            "og_image": has_og_image, "twitter_card": has_twitter_card,
            "score": meta_score,
        }

        if not has_title or not has_description:
            findings.append({"severity": "high", "title": "Missing Essential Meta Tags",
                            "description": "Title or meta description is missing."})
            recommendations.append("Add title and meta description to every page")

        if not has_og_title:
            recommendations.append("Add Open Graph tags (og:title, og:description, og:image)")

        # ── 5. H1 Tags ──
        h1_tags = page_data.get("h1_tags", [])
        checks["h1_count"] = len(h1_tags)
        if len(h1_tags) == 0:
            findings.append({"severity": "medium", "title": "Missing H1 Tag",
                            "description": "No H1 heading found on the page."})
        elif len(h1_tags) > 1:
            findings.append({"severity": "medium", "title": f"Multiple H1 Tags ({len(h1_tags)})",
                            "description": "Multiple H1 tags can confuse search engines."})

        # ── 6. Images ──
        images = page_data.get("images", [])
        total_images = len(images)
        images_with_alt = sum(1 for img in images if img.get("alt"))
        alt_coverage = (images_with_alt / total_images * 100) if total_images > 0 else 100
        checks["images"] = {
            "total": total_images,
            "with_alt": images_with_alt,
            "alt_coverage": round(alt_coverage, 1),
        }
        if total_images > 0 and alt_coverage < 50:
            findings.append({"severity": "medium", "title": "Poor Image Alt Text Coverage",
                            "description": f"Only {alt_coverage:.0f}% of images have alt text."})
            recommendations.append("Add descriptive alt text to all images")

        # ── 7. Redirect chain ──
        redirects = page_data.get("redirect_chain", [])
        checks["redirect_chain_length"] = len(redirects)
        if len(redirects) > 2:
            findings.append({"severity": "medium", "title": f"Long Redirect Chain ({len(redirects)} hops)",
                            "description": "Excessive redirects slow crawling."})

        # ── Composite score ──
        score = 0
        score += 15 if is_https else 0
        score += 15 if has_ssr else 0
        score += min(15, len(present_headers) * 3)
        score += min(20, meta_score // 5)
        score += 10 if len(h1_tags) == 1 else 0
        score += 10 if alt_coverage >= 80 else (5 if alt_coverage >= 50 else 0)
        score += 10 if len(redirects) <= 1 else (5 if len(redirects) <= 2 else 0)
        score += 5 if has_viewport else 0
        score = min(100, score)

        return {
            "scores": {"technical": score},
            "findings": findings,
            "recommendations": recommendations,
            "details": {"checks": checks},
        }
