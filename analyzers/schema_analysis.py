"""
Analyzer 5: Schema & Structured Data
JSON-LD detection, validation, and recommendation generation.
"""
import json
import re
from pathlib import Path

from analyzers.base import AnalyzerBase

TEMPLATE_DIR = Path(__file__).parent.parent / "data" / "schema_templates"

# Expected schema types per business type
EXPECTED_SCHEMAS = {
    "local_business": ["LocalBusiness", "Organization", "BreadcrumbList"],
    "national_brand": ["Organization", "WebSite", "BreadcrumbList"],
    "digital_service": ["SoftwareApplication", "Organization", "WebSite", "BreadcrumbList"],
    "informational": ["Article", "Organization", "WebSite", "BreadcrumbList"],
    "ecommerce": ["Product", "Organization", "WebSite", "BreadcrumbList"],
    "agency": ["Organization", "ProfessionalService", "WebSite", "BreadcrumbList"],
}


class SchemaAnalyzer(AnalyzerBase):
    name = "schema_analysis"

    async def analyze(self, page_data: dict, business_type: str, api_keys: dict = None) -> dict:
        structured_data = page_data.get("structured_data", [])
        html = page_data.get("html", "")
        findings = []
        recommendations = []

        # ── Detect all schema types present ──
        found_types = set()
        all_schemas = []
        for sd in structured_data:
            if isinstance(sd, dict):
                t = sd.get("@type", "")
                if isinstance(t, list):
                    found_types.update(t)
                else:
                    found_types.add(t)
                all_schemas.append(sd)
                # Check @graph
                for item in sd.get("@graph", []):
                    if isinstance(item, dict):
                        gt = item.get("@type", "")
                        if isinstance(gt, list):
                            found_types.update(gt)
                        else:
                            found_types.add(gt)
                        all_schemas.append(item)
            elif isinstance(sd, list):
                for item in sd:
                    if isinstance(item, dict):
                        found_types.add(item.get("@type", ""))
                        all_schemas.append(item)

        found_types.discard("")

        if not found_types:
            findings.append({
                "severity": "critical",
                "title": "No Structured Data Found",
                "description": "No JSON-LD schema markup detected. AI models rely on structured data to understand entities.",
            })
            recommendations.append("Add Organization schema with name, url, logo, and sameAs properties")
            recommendations.append("Add page-appropriate schema (Article, Product, LocalBusiness, etc.)")
            return {
                "scores": {"schema": 0},
                "findings": findings,
                "recommendations": recommendations,
                "details": {"found_types": [], "expected_types": EXPECTED_SCHEMAS.get(business_type, [])},
            }

        # ── Check against expected types ──
        expected = set(EXPECTED_SCHEMAS.get(business_type, EXPECTED_SCHEMAS["informational"]))
        # Flexible matching: LocalBusiness subtypes count
        local_subtypes = {"Restaurant", "Store", "MedicalBusiness", "LegalService",
                         "Dentist", "Plumber", "Electrician", "FinancialService"}
        if "LocalBusiness" in expected and (found_types & local_subtypes):
            expected.discard("LocalBusiness")

        missing_types = expected - found_types
        matched_types = expected & found_types

        # ── Validate schema quality ──
        quality_checks = {
            "has_name": False,
            "has_url": False,
            "has_same_as": False,
            "has_logo": False,
            "has_description": False,
            "has_author": False,
            "has_date_published": False,
            "has_breadcrumb": False,
        }

        for schema in all_schemas:
            if schema.get("name"):
                quality_checks["has_name"] = True
            if schema.get("url"):
                quality_checks["has_url"] = True
            if schema.get("sameAs"):
                quality_checks["has_same_as"] = True
            if schema.get("logo"):
                quality_checks["has_logo"] = True
            if schema.get("description"):
                quality_checks["has_description"] = True
            if schema.get("author"):
                quality_checks["has_author"] = True
            if schema.get("datePublished"):
                quality_checks["has_date_published"] = True
            if schema.get("@type") == "BreadcrumbList":
                quality_checks["has_breadcrumb"] = True

        # ── Scoring ──
        score = 0

        # Types present (40 points)
        if found_types:
            score += 15  # Has any schema
        type_coverage = len(matched_types) / max(len(expected), 1)
        score += int(type_coverage * 25)

        # Quality checks (40 points)
        quality_points = sum(5 for v in quality_checks.values() if v)
        score += quality_points

        # sameAs bonus (important for GEO)
        if quality_checks["has_same_as"]:
            score += 10
        else:
            findings.append({
                "severity": "medium",
                "title": "Missing sameAs Links",
                "description": "No sameAs property found in schema. This links your entity to profiles on other platforms.",
            })
            recommendations.append("Add sameAs links to your Wikipedia, LinkedIn, social media, and directory profiles")

        # Breadcrumb bonus
        if quality_checks["has_breadcrumb"]:
            score += 5

        score = min(100, score)

        # ── Missing type findings ──
        if missing_types:
            findings.append({
                "severity": "high",
                "title": f"Missing Expected Schema Types",
                "description": f"For a {business_type} site, expected but not found: {', '.join(missing_types)}",
            })
            for mt in missing_types:
                recommendations.append(f"Add {mt} schema markup")

        # ── Load template for recommendation ──
        template_map = {
            "local_business": "local-business.json",
            "digital_service": "software-saas.json",
            "ecommerce": "product-ecommerce.json",
            "informational": "article-author.json",
            "national_brand": "organization.json",
            "agency": "organization.json",
        }
        template_file = TEMPLATE_DIR / template_map.get(business_type, "organization.json")
        recommended_schema = None
        if template_file.exists():
            try:
                recommended_schema = json.loads(template_file.read_text())
            except Exception:
                pass

        return {
            "scores": {"schema": score},
            "findings": findings,
            "recommendations": recommendations,
            "details": {
                "found_types": sorted(found_types),
                "expected_types": sorted(expected),
                "missing_types": sorted(missing_types) if missing_types else [],
                "quality_checks": quality_checks,
                "schema_count": len(all_schemas),
                "recommended_template": recommended_schema,
            },
        }
