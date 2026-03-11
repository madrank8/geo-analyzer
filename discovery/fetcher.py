"""
Async page fetcher for GEO analysis.
Ported from geo-seo-claude/scripts/fetch_page.py — converted to async httpx.
"""
import json
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

AI_CRAWLERS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "anthropic-ai",
    "PerplexityBot", "CCBot", "Bytespider", "cohere-ai", "Google-Extended",
    "GoogleOther", "Applebot-Extended", "FacebookBot", "Amazonbot",
]


async def fetch_page(url: str, timeout: int = 30) -> dict:
    """Fetch a page and return structured analysis data."""
    result = {
        "url": url, "status_code": None, "redirect_chain": [],
        "headers": {}, "meta_tags": {}, "title": None, "description": None,
        "canonical": None, "h1_tags": [], "heading_structure": [],
        "word_count": 0, "text_content": "", "html": "",
        "internal_links": [], "external_links": [], "images": [],
        "structured_data": [], "has_ssr_content": True,
        "security_headers": {}, "errors": [],
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url, headers=DEFAULT_HEADERS)

        if response.history:
            result["redirect_chain"] = [
                {"url": str(r.url), "status": r.status_code} for r in response.history
            ]

        result["status_code"] = response.status_code
        result["headers"] = dict(response.headers)
        result["html"] = response.text

        # Security headers
        for header in ["Strict-Transport-Security", "Content-Security-Policy",
                       "X-Frame-Options", "X-Content-Type-Options",
                       "Referrer-Policy", "Permissions-Policy"]:
            result["security_headers"][header] = response.headers.get(header)

        soup = BeautifulSoup(response.text, "lxml")

        # Title
        title_tag = soup.find("title")
        result["title"] = title_tag.get_text(strip=True) if title_tag else None

        # Meta tags
        for meta in soup.find_all("meta"):
            name = meta.get("name", meta.get("property", ""))
            content = meta.get("content", "")
            if name and content:
                result["meta_tags"][name.lower()] = content
                if name.lower() == "description":
                    result["description"] = content

        # Canonical
        canonical = soup.find("link", rel="canonical")
        result["canonical"] = canonical.get("href") if canonical else None

        # Headings
        for level in range(1, 7):
            for heading in soup.find_all(f"h{level}"):
                text = heading.get_text(strip=True)
                result["heading_structure"].append({"level": level, "text": text})
                if level == 1:
                    result["h1_tags"].append(text)

        # Text content (strip non-content elements)
        for element in soup.find_all(["script", "style", "nav", "footer", "header"]):
            element.decompose()
        text = soup.get_text(separator=" ", strip=True)
        result["text_content"] = text
        result["word_count"] = len(text.split())

        # Links
        parsed_url = urlparse(url)
        base_domain = parsed_url.netloc
        for link in soup.find_all("a", href=True):
            href = urljoin(url, link["href"])
            link_text = link.get_text(strip=True)
            parsed_href = urlparse(href)
            if parsed_href.netloc == base_domain:
                result["internal_links"].append({"url": href, "text": link_text})
            elif parsed_href.scheme in ("http", "https"):
                result["external_links"].append({"url": href, "text": link_text})

        # Images
        for img in BeautifulSoup(response.text, "lxml").find_all("img"):
            result["images"].append({
                "src": img.get("src", ""), "alt": img.get("alt", ""),
                "width": img.get("width"), "height": img.get("height"),
                "loading": img.get("loading"),
            })

        # Structured data (JSON-LD)
        for script in BeautifulSoup(response.text, "lxml").find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                result["structured_data"].append(data)
            except (json.JSONDecodeError, TypeError):
                result["errors"].append("Invalid JSON-LD detected")

        # SSR check
        js_app_roots = BeautifulSoup(response.text, "lxml").find_all(
            id=re.compile(r"(app|root|__next|__nuxt)", re.I)
        )
        if js_app_roots:
            for root in js_app_roots:
                inner_text = root.get_text(strip=True)
                if len(inner_text) < 50:
                    result["has_ssr_content"] = False
                    result["errors"].append(
                        f"Possible client-side only rendering: #{root.get('id', 'unknown')} has minimal server-rendered content"
                    )

    except httpx.TimeoutException:
        result["errors"].append(f"Timeout after {timeout} seconds")
    except httpx.ConnectError as e:
        result["errors"].append(f"Connection error: {str(e)}")
    except Exception as e:
        result["errors"].append(f"Unexpected error: {str(e)}")

    return result


async def fetch_robots_txt(url: str, timeout: int = 15) -> dict:
    """Fetch and parse robots.txt for AI crawler directives."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    result = {
        "url": robots_url, "exists": False, "content": "",
        "ai_crawler_status": {}, "sitemaps": [], "errors": [],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(robots_url, headers=DEFAULT_HEADERS)

        if response.status_code == 200:
            result["exists"] = True
            result["content"] = response.text

            lines = response.text.split("\n")
            current_agent = None
            agent_rules = {}

            for line in lines:
                line = line.strip()
                if line.lower().startswith("user-agent:"):
                    current_agent = line.split(":", 1)[1].strip()
                    if current_agent not in agent_rules:
                        agent_rules[current_agent] = []
                elif line.lower().startswith("disallow:") and current_agent:
                    path = line.split(":", 1)[1].strip()
                    agent_rules[current_agent].append({"directive": "Disallow", "path": path})
                elif line.lower().startswith("allow:") and current_agent:
                    path = line.split(":", 1)[1].strip()
                    agent_rules[current_agent].append({"directive": "Allow", "path": path})
                elif line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if not sitemap_url.startswith("http"):
                        sitemap_url = "http" + sitemap_url
                    result["sitemaps"].append(sitemap_url)

            for crawler in AI_CRAWLERS:
                if crawler in agent_rules:
                    rules = agent_rules[crawler]
                    if any(r["directive"] == "Disallow" and r["path"] == "/" for r in rules):
                        result["ai_crawler_status"][crawler] = "BLOCKED"
                    elif any(r["directive"] == "Disallow" and r["path"] for r in rules):
                        result["ai_crawler_status"][crawler] = "PARTIALLY_BLOCKED"
                    else:
                        result["ai_crawler_status"][crawler] = "ALLOWED"
                elif "*" in agent_rules:
                    wildcard_rules = agent_rules["*"]
                    if any(r["directive"] == "Disallow" and r["path"] == "/" for r in wildcard_rules):
                        result["ai_crawler_status"][crawler] = "BLOCKED_BY_WILDCARD"
                    else:
                        result["ai_crawler_status"][crawler] = "ALLOWED_BY_DEFAULT"
                else:
                    result["ai_crawler_status"][crawler] = "NOT_MENTIONED"

        elif response.status_code == 404:
            result["errors"].append("No robots.txt found (404)")
            for crawler in AI_CRAWLERS:
                result["ai_crawler_status"][crawler] = "NO_ROBOTS_TXT"
        else:
            result["errors"].append(f"Unexpected status code: {response.status_code}")

    except Exception as e:
        result["errors"].append(f"Error fetching robots.txt: {str(e)}")

    return result


async def fetch_llms_txt(url: str, timeout: int = 15) -> dict:
    """Check for llms.txt and llms-full.txt files."""
    parsed = urlparse(url)
    llms_url = f"{parsed.scheme}://{parsed.netloc}/llms.txt"
    llms_full_url = f"{parsed.scheme}://{parsed.netloc}/llms-full.txt"

    result = {
        "llms_txt": {"url": llms_url, "exists": False, "content": ""},
        "llms_full_txt": {"url": llms_full_url, "exists": False, "content": ""},
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        for key, check_url in [("llms_txt", llms_url), ("llms_full_txt", llms_full_url)]:
            try:
                response = await client.get(check_url, headers=DEFAULT_HEADERS)
                if response.status_code == 200:
                    result[key]["exists"] = True
                    result[key]["content"] = response.text
            except Exception as e:
                result["errors"].append(f"Error checking {check_url}: {str(e)}")

    return result


def extract_content_blocks(html: str) -> list:
    """Extract content blocks for citability analysis."""
    soup = BeautifulSoup(html, "lxml")

    for element in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()

    blocks = []
    current_heading = None
    current_content = []

    for element in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table", "blockquote"]
    ):
        tag = element.name
        if tag.startswith("h"):
            if current_content:
                text = " ".join(current_content)
                blocks.append({
                    "heading": current_heading,
                    "content": text,
                    "word_count": len(text.split()),
                })
            current_heading = element.get_text(strip=True)
            current_content = []
        else:
            text = element.get_text(strip=True)
            if text:
                current_content.append(text)

    if current_content:
        text = " ".join(current_content)
        blocks.append({
            "heading": current_heading,
            "content": text,
            "word_count": len(text.split()),
        })

    return blocks


async def crawl_sitemap(url: str, max_pages: int = 50, timeout: int = 15) -> list:
    """Crawl sitemap.xml to discover pages."""
    parsed = urlparse(url)
    sitemap_urls = [
        f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
        f"{parsed.scheme}://{parsed.netloc}/sitemap_index.xml",
    ]

    discovered_pages = set()

    async with httpx.AsyncClient(timeout=timeout) as client:
        for sitemap_url in sitemap_urls:
            try:
                response = await client.get(sitemap_url, headers=DEFAULT_HEADERS)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, "lxml")

                # Sitemap index
                for sitemap in soup.find_all("sitemap"):
                    loc = sitemap.find("loc")
                    if loc and len(discovered_pages) < max_pages:
                        try:
                            child_resp = await client.get(loc.text.strip(), headers=DEFAULT_HEADERS)
                            if child_resp.status_code == 200:
                                child_soup = BeautifulSoup(child_resp.text, "lxml")
                                for url_tag in child_soup.find_all("url"):
                                    loc_tag = url_tag.find("loc")
                                    if loc_tag:
                                        discovered_pages.add(loc_tag.text.strip())
                                    if len(discovered_pages) >= max_pages:
                                        break
                        except Exception:
                            pass

                # Direct URL entries
                for url_tag in soup.find_all("url"):
                    loc = url_tag.find("loc")
                    if loc:
                        discovered_pages.add(loc.text.strip())
                    if len(discovered_pages) >= max_pages:
                        break

                if discovered_pages:
                    break

            except Exception:
                continue

    return list(discovered_pages)[:max_pages]
