"""Google Gemini API integration for content dimension scoring."""
import json
import httpx
from config import API_KEYS


async def gemini_score_dimensions(text_stats: dict, nlp_data: dict,
                                   text_content: str, client: httpx.AsyncClient = None) -> dict:
    """Use Gemini to score content across quality dimensions."""
    key = API_KEYS["gemini_api_key"]
    if not key:
        return {"status": "skipped", "reason": "Gemini API key not configured"}

    should_close = False
    if client is None:
        client = httpx.AsyncClient()
        should_close = True

    try:
        context_parts = []
        if text_stats:
            context_parts.append(f"Text Statistics: word_count={text_stats.get('word_count', 0)}, "
                                f"fk_grade={text_stats.get('fk_grade', 0):.1f}, "
                                f"lexical_diversity={text_stats.get('type_token_ratio', 0):.3f}, "
                                f"passive_ratio={text_stats.get('passive_ratio', 0):.3f}")

        if nlp_data and nlp_data.get("entities"):
            context_parts.append(f"NLP Entities: {json.dumps(nlp_data['entities'][:5])}")
        if nlp_data and nlp_data.get("categories"):
            context_parts.append(f"NLP Categories: {json.dumps(nlp_data['categories'])}")

        content_preview = text_content[:3000] if text_content else ""

        prompt = f"""You are a content quality analyst. Score this content across these dimensions (0-100 each).

MEASURED DATA:
{chr(10).join(context_parts)}

CONTENT PREVIEW:
{content_preview}

Score each dimension 0-100 with a brief justification:
1. entity_grounding - How well entities are identified and linked to authoritative sources
2. eeat_depth - Experience, Expertise, Authoritativeness, Trustworthiness signals
3. content_originality - Unique insights, data, or perspectives vs generic content
4. nlp_clarity - How clearly the NLP can extract entities and meaning
5. passage_ranking - How well individual passages serve as direct answers
6. semantic_depth - Depth of topical coverage and concept interconnection
7. intent_alignment - How well content matches likely search intent
8. freshness - Currency of information, dates, and references
9. structural_optimization - Heading hierarchy, content organization, scanability
10. readability - Reading level appropriateness and accessibility

Return ONLY valid JSON in this format:
{{"dimensions": {{"entity_grounding": {{"score": N, "note": "..."}}, ...}}}}"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        resp = await client.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000},
        }, timeout=30)

        if resp.status_code != 200:
            return {"status": "error", "reason": f"Gemini returned {resp.status_code}"}

        text_resp = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")

        # Extract JSON from response
        json_match = text_resp
        if "```json" in text_resp:
            json_match = text_resp.split("```json")[1].split("```")[0]
        elif "```" in text_resp:
            json_match = text_resp.split("```")[1].split("```")[0]

        try:
            parsed = json.loads(json_match.strip())
            return {"status": "success", "dimensions": parsed.get("dimensions", parsed)}
        except json.JSONDecodeError:
            return {"status": "error", "reason": "Failed to parse Gemini response as JSON"}

    except Exception as e:
        return {"status": "error", "reason": str(e)}
    finally:
        if should_close:
            await client.aclose()
