"""Google Places API integration — extracted from EntityOS."""
import httpx
from config import API_KEYS


async def places_verify(place_id: str, client: httpx.AsyncClient = None) -> dict:
    """Verify and enrich entity data via Google Places API (New)."""
    key = API_KEYS["places_api_key"]
    if not key:
        return {"status": "skipped", "reason": "Places API key not configured"}
    if not place_id:
        return {"status": "skipped", "reason": "No Place ID found"}

    should_close = False
    if client is None:
        client = httpx.AsyncClient()
        should_close = True

    try:
        url = f"https://places.googleapis.com/v1/places/{place_id}"
        headers = {
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": (
                "id,displayName,formattedAddress,rating,userRatingCount,reviews,"
                "types,websiteUri,currentOpeningHours,nationalPhoneNumber,"
                "editorialSummary,primaryType,primaryTypeDisplayName,googleMapsUri"
            ),
        }

        resp = await client.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {"status": "error", "reason": f"Places API returned {resp.status_code}"}

        place = resp.json()
        live_data = {
            "name": place.get("displayName", {}).get("text", ""),
            "address": place.get("formattedAddress", ""),
            "rating": place.get("rating"),
            "review_count": place.get("userRatingCount", 0),
            "phone": place.get("nationalPhoneNumber", ""),
            "website": place.get("websiteUri", ""),
            "primary_type": place.get("primaryTypeDisplayName", {}).get("text", ""),
            "types": place.get("types", []),
            "maps_url": place.get("googleMapsUri", ""),
            "editorial_summary": place.get("editorialSummary", {}).get("text", ""),
        }

        reviews = []
        for rev in place.get("reviews", [])[:5]:
            reviews.append({
                "author": rev.get("authorAttribution", {}).get("displayName", ""),
                "rating": rev.get("rating"),
                "text": rev.get("text", {}).get("text", "")[:200],
                "time": rev.get("relativePublishTimeDescription", ""),
            })
        live_data["reviews_sample"] = reviews

        hours = place.get("currentOpeningHours", {})
        if hours:
            live_data["open_now"] = hours.get("openNow")
            live_data["hours_text"] = [d.strip() for d in hours.get("weekdayDescriptions", [])]

        return {"status": "success", "live_data": live_data, "place_id": place_id}

    except Exception as e:
        return {"status": "error", "reason": str(e)}
    finally:
        if should_close:
            await client.aclose()
