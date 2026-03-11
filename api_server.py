#!/usr/bin/env python3
"""
GEO Analyzer API Server
Combined web app for Generative Engine Optimization analysis.
"""
import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from config import API_KEYS, PLAN_LIMITS
from db import init_db, get_db
from auth import log_usage
from models import GeoAnalyzeRequest

from discovery.fetcher import fetch_page
from discovery.business_detector import detect_business_type

from analyzers.ai_visibility import AIVisibilityAnalyzer
from analyzers.platform_analysis import PlatformAnalyzer
from analyzers.technical import TechnicalAnalyzer
from analyzers.content_quality import ContentQualityAnalyzer
from analyzers.schema_analysis import SchemaAnalyzer

from scoring.geo_scorer import compute_geo_score, generate_action_plan
from scoring.dimension_mapper import map_dimensions_to_geo, blend_scores

from reports.markdown_report import generate_markdown_report

from engines.veto_engine import run_vetoes


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="GEO Analyzer", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory analysis tracking (for async progress)
_analyses = {}


@app.get("/api/health")
async def health():
    has_keys = {k: bool(v) for k, v in API_KEYS.items()}
    return {"status": "ok", "api_keys_configured": has_keys}


# ════════════════════════════════════════════════════════════════
#  GEO ANALYSIS ENDPOINTS
# ════════════════════════════════════════════════════════════════

@app.post("/api/geo/analyze")
async def start_analysis(payload: GeoAnalyzeRequest):
    analysis_id = str(uuid.uuid4())

    # Store in DB
    db = get_db()
    db.execute(
        "INSERT INTO geo_analyses (id, user_id, url, brand_name, status) VALUES (?, ?, ?, ?, 'running')",
        (analysis_id, 0, payload.url, payload.brand_name),
    )
    db.commit()
    db.close()

    log_usage(0, "geo_analyze", payload.url)

    # Track progress in memory
    _analyses[analysis_id] = {"status": "running", "progress": {}}

    # Launch async analysis
    asyncio.create_task(_run_analysis(analysis_id, payload.url, payload.brand_name))

    return {"analysis_id": analysis_id, "status": "running"}


async def _run_analysis(analysis_id: str, url: str, brand_name: str = None):
    """Run the full GEO analysis pipeline."""
    progress = _analyses.get(analysis_id, {}).get("progress", {})

    try:
        # ── Phase 1: Fetch page ──
        progress["fetch"] = "running"
        page_data = await fetch_page(url)
        progress["fetch"] = "complete"

        if page_data.get("status_code") and page_data["status_code"] >= 400:
            _analyses[analysis_id] = {
                "status": "error",
                "error": f"Page returned HTTP {page_data['status_code']}",
            }
            _save_analysis(analysis_id, "error", None, error=f"HTTP {page_data['status_code']}")
            return

        # ── Phase 2: Detect business type ──
        progress["detect"] = "running"
        btype = detect_business_type(
            page_data.get("html", ""),
            page_data.get("text_content", ""),
            url,
            page_data.get("structured_data", []),
        )
        business_type = btype["type"]
        progress["detect"] = "complete"

        # ── Phase 3: Run 5 analyzers in parallel ──
        analyzers = [
            AIVisibilityAnalyzer(),
            PlatformAnalyzer(),
            TechnicalAnalyzer(),
            ContentQualityAnalyzer(),
            SchemaAnalyzer(),
        ]

        for a in analyzers:
            progress[a.name] = "running"

        # Pass crawler status to platform analyzer
        results = await asyncio.gather(*[
            a.analyze(page_data, business_type, API_KEYS) for a in analyzers
        ], return_exceptions=True)

        all_scores = {}
        all_findings = []
        all_recommendations = []
        all_details = {}

        for analyzer, result in zip(analyzers, results):
            progress[analyzer.name] = "complete"
            if isinstance(result, Exception):
                progress[analyzer.name] = f"error: {str(result)}"
                continue
            all_scores.update(result.get("scores", {}))
            all_findings.extend(result.get("findings", []))
            all_recommendations.extend(result.get("recommendations", []))
            all_details[analyzer.name] = result.get("details", {})

        # Pass crawler data to platform analyzer result
        crawler_status = all_details.get("ai_visibility", {}).get("crawlers", {}).get("status", {})
        if crawler_status:
            # Re-run platform analyzer with crawler data
            page_data["_crawler_status"] = crawler_status
            platform_result = await PlatformAnalyzer().analyze(page_data, business_type, API_KEYS)
            all_scores.update(platform_result.get("scores", {}))
            all_details["platform_analysis"] = platform_result.get("details", {})

        # ── Phase 4: Run veto engine ──
        progress["veto"] = "running"
        html_signals = {
            "title": page_data.get("title", ""),
            "h1_texts": page_data.get("h1_tags", []),
        }
        veto_result = run_vetoes(
            html=page_data.get("html", ""),
            text=page_data.get("text_content", ""),
            html_signals=html_signals,
            scan_context={"url": url},
        )
        progress["veto"] = "complete"

        # Add veto findings
        for veto in veto_result.get("triggered_vetoes", []):
            all_findings.append({
                "severity": veto["severity"],
                "title": f"Trust Veto: {veto['name']}",
                "description": veto["evidence"],
            })

        # ── Phase 5: Compute GEO score ──
        # Brand authority: derive from KG presence signals + schema sameAs
        brand_score = 40  # base
        schema_details = all_details.get("schema_analysis", {})
        if schema_details.get("quality_checks", {}).get("has_same_as"):
            brand_score += 20
        if page_data.get("structured_data"):
            brand_score += 15
        content_details = all_details.get("content_quality", {})
        if content_details.get("nlp_data") and content_details["nlp_data"].get("entities"):
            entities = content_details["nlp_data"]["entities"]
            if any(e.get("mid") for e in entities):
                brand_score += 25
        all_scores["brand_authority"] = min(100, brand_score)

        score_result = compute_geo_score(all_scores)
        action_plan = generate_action_plan(all_findings, all_scores)

        # ── Phase 6: Build final result ──
        platforms = all_details.get("platform_analysis", {}).get("platforms", {})
        crawler_details = all_details.get("ai_visibility", {}).get("crawlers", {})

        final_result = {
            "url": url,
            "brand_name": brand_name or page_data.get("title", url),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "business_type": btype,
            "geo_score": score_result["geo_score"],
            "grade": score_result["grade"],
            "label": score_result["label"],
            "scores": score_result["scores"],
            "weights": score_result["weights"],
            "platforms": platforms,
            "findings": all_findings,
            "recommendations": list(set(all_recommendations)),
            "action_plan": action_plan,
            "crawler_access": crawler_details.get("status", {}),
            "veto_result": {
                "certification_status": veto_result["certification_status"],
                "certification_reason": veto_result["certification_reason"],
                "triggered_count": veto_result["veto_count"],
            },
            "details": all_details,
        }

        _analyses[analysis_id] = {"status": "complete", "result": final_result, "progress": progress}
        _save_analysis(analysis_id, "complete", final_result)

    except Exception as e:
        _analyses[analysis_id] = {"status": "error", "error": str(e), "progress": progress}
        _save_analysis(analysis_id, "error", None, error=str(e))


def _save_analysis(analysis_id: str, status: str, result: dict, error: str = None):
    """Persist analysis result to DB."""
    db = get_db()
    if status == "complete" and result:
        db.execute(
            "UPDATE geo_analyses SET status = ?, result = ?, geo_score = ?, business_type = ?, completed_at = datetime('now') WHERE id = ?",
            (status, json.dumps(result), result.get("geo_score"), result.get("business_type", {}).get("type", ""), analysis_id),
        )
    else:
        db.execute(
            "UPDATE geo_analyses SET status = ?, result = ? WHERE id = ?",
            (status, json.dumps({"error": error or "Unknown error"}), analysis_id),
        )
    db.commit()
    db.close()


@app.get("/api/geo/status/{analysis_id}")
async def get_status(analysis_id: str):
    # Check in-memory first
    if analysis_id in _analyses:
        data = _analyses[analysis_id]
        response = {"status": data["status"], "progress": data.get("progress", {})}
        if data["status"] == "complete":
            response["result"] = data.get("result")
        elif data["status"] == "error":
            response["error"] = data.get("error")
        return response

    # Fall back to DB
    db = get_db()
    row = db.execute("SELECT * FROM geo_analyses WHERE id = ?",
                     (analysis_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Analysis not found")

    response = {"status": row["status"]}
    if row["result"]:
        try:
            response["result"] = json.loads(row["result"])
        except json.JSONDecodeError:
            pass
    return response


@app.get("/api/geo/result/{analysis_id}")
async def get_result(analysis_id: str):
    # Check in-memory
    if analysis_id in _analyses and _analyses[analysis_id]["status"] == "complete":
        return _analyses[analysis_id]["result"]

    # Fall back to DB
    db = get_db()
    row = db.execute("SELECT * FROM geo_analyses WHERE id = ?",
                     (analysis_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Analysis not found")
    if row["status"] != "complete":
        raise HTTPException(400, f"Analysis status: {row['status']}")

    try:
        return json.loads(row["result"])
    except json.JSONDecodeError:
        raise HTTPException(500, "Corrupt analysis data")


@app.get("/api/geo/report/{analysis_id}/md")
async def get_markdown_report(analysis_id: str):
    result = await get_result(analysis_id)
    md = generate_markdown_report(result)
    return PlainTextResponse(md, media_type="text/markdown",
                             headers={"Content-Disposition": f"attachment; filename=geo-report-{analysis_id[:8]}.md"})


@app.get("/api/geo/report/{analysis_id}/pdf")
async def get_pdf_report(analysis_id: str):
    result = await get_result(analysis_id)
    import tempfile
    from reports.pdf_report import generate_report

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        output_path = f.name

    await asyncio.to_thread(generate_report, result, output_path)
    return FileResponse(output_path, media_type="application/pdf",
                       filename=f"geo-report-{analysis_id[:8]}.pdf")


@app.get("/api/geo/history")
async def get_history():
    db = get_db()
    rows = db.execute(
        "SELECT id, url, brand_name, business_type, status, geo_score, created_at, completed_at "
        "FROM geo_analyses ORDER BY created_at DESC LIMIT 50",
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ── Entity resolution endpoint (from EntityOS) ──
@app.post("/api/entity/resolve")
async def entity_resolve(request: Request):
    body = await request.json()
    query = body.get("query", "")
    website = body.get("website", "")
    if not query:
        raise HTTPException(400, "Query is required")

    from google_apis.knowledge_graph import kg_resolve
    result = await kg_resolve(query, website)
    return result


# ── Serve SPA ──
@app.get("/")
async def serve_root():
    return FileResponse("static/index.html")


@app.get("/{path:path}")
async def serve_spa(path: str):
    import os
    static_path = os.path.join("static", path)
    if os.path.isfile(static_path):
        return FileResponse(static_path)
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
