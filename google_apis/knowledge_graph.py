"""Google Knowledge Graph API integration — extracted from EntityOS."""
import httpx
from config import API_KEYS


async def kg_resolve(query: str, website: str = "", client: httpx.AsyncClient = None) -> dict:
    """Resolve an entity via Google Knowledge Graph API."""
    key = API_KEYS["kg_api_key"]
    if not key:
        return {"status": "skipped", "reason": "KG API key not configured"}

    should_close = False
    if client is None:
        client = httpx.AsyncClient()
        should_close = True

    try:
        url = "https://kgsearch.googleapis.com/v1/entities:search"
        params = {"query": query, "key": key, "limit": 5, "indent": True}
        resp = await client.get(url, params=params, timeout=15)
        data = resp.json()

        entities = []
        best_match = None
        for item in data.get("itemListElement", []):
            result = item.get("result", {})
            entity = {
                "name": result.get("name", ""),
                "mid": result.get("@id", ""),
                "types": result.get("@type", []),
                "description": result.get("description", ""),
                "detailed_description": "",
                "url": result.get("url", ""),
                "image": "",
                "result_score": item.get("resultScore", 0),
                "identifiers": {},
            }
            dd = result.get("detailedDescription", {})
            if dd:
                entity["detailed_description"] = dd.get("articleBody", "")

            img = result.get("image", {})
            if img:
                entity["image"] = img.get("contentUrl", "")

            for ident in result.get("identifier", []):
                prop_id = ident.get("propertyID", "")
                val = ident.get("value", "")
                if prop_id and val:
                    entity["identifiers"][prop_id] = val

            entities.append(entity)

            if website and result.get("url", ""):
                entity_url = result.get("url", "").lower().rstrip("/")
                check_url = website.lower().rstrip("/").replace("https://", "").replace("http://", "").replace("www.", "")
                if check_url in entity_url or entity_url.replace("http://", "").replace("https://", "").replace("www.", "") in check_url:
                    best_match = entity

        if not best_match and entities:
            best_match = entities[0]

        place_id = ""
        if best_match:
            place_id = best_match.get("identifiers", {}).get("googlePlaceID", "")

        return {
            "status": "success",
            "entity": best_match,
            "all_entities": entities[:5],
            "is_local": bool(place_id),
            "place_id": place_id,
            "entity_count": len(entities),
        }
    except Exception as e:
        return {"status": "error", "reason": str(e)}
    finally:
        if should_close:
            await client.aclose()
