"""Google Cloud Natural Language API integration — extracted from EntityOS."""
import httpx
from config import API_KEYS


async def nlp_classify(text: str, client: httpx.AsyncClient = None) -> dict:
    """Run NLP entity extraction, classification, and sentiment analysis."""
    key = API_KEYS["nlp_api_key"] or API_KEYS["kg_api_key"]
    if not key:
        return {"status": "skipped", "reason": "NLP API key not configured"}
    if not text or len(text.strip()) < 20:
        return {"status": "skipped", "reason": "Not enough text to analyze"}

    should_close = False
    if client is None:
        client = httpx.AsyncClient()
        should_close = True

    try:
        base_url = "https://language.googleapis.com/v1/documents"
        document = {"type": "PLAIN_TEXT", "content": text[:5000]}

        # Entity extraction
        entities_result = []
        try:
            resp = await client.post(
                f"{base_url}:analyzeEntities?key={key}",
                json={"document": document, "encodingType": "UTF8"},
                timeout=15,
            )
            if resp.status_code == 200:
                for ent in resp.json().get("entities", [])[:10]:
                    entities_result.append({
                        "name": ent.get("name", ""),
                        "type": ent.get("type", "UNKNOWN"),
                        "salience": round(ent.get("salience", 0), 4),
                        "mid": ent.get("metadata", {}).get("mid", ""),
                        "wikipedia_url": ent.get("metadata", {}).get("wikipedia_url", ""),
                        "mention_count": len(ent.get("mentions", [])),
                    })
        except Exception:
            pass

        # Content classification
        categories = []
        try:
            resp2 = await client.post(
                f"{base_url}:classifyText?key={key}",
                json={"document": document},
                timeout=15,
            )
            if resp2.status_code == 200:
                for cat in resp2.json().get("categories", []):
                    categories.append({
                        "name": cat.get("name", ""),
                        "confidence": round(cat.get("confidence", 0), 4),
                    })
        except Exception:
            pass

        # Sentiment analysis
        sentiment = {}
        try:
            resp3 = await client.post(
                f"{base_url}:analyzeSentiment?key={key}",
                json={"document": document, "encodingType": "UTF8"},
                timeout=15,
            )
            if resp3.status_code == 200:
                doc_sent = resp3.json().get("documentSentiment", {})
                sentiment = {
                    "score": round(doc_sent.get("score", 0), 4),
                    "magnitude": round(doc_sent.get("magnitude", 0), 4),
                }
        except Exception:
            pass

        return {
            "status": "success",
            "entities": entities_result,
            "categories": categories,
            "sentiment": sentiment,
        }

    except Exception as e:
        return {"status": "error", "reason": str(e)}
    finally:
        if should_close:
            await client.aclose()
