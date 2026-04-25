import logging
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JD-Explorer/1.0)"}
_JS_THRESHOLD = 100


async def fetch_page_text(url: str, max_chars: int = 8000) -> str:
    text = await _fetch_httpx(url, max_chars)
    word_count = len(text.split())
    if word_count < _JS_THRESHOLD:
        log.info("[scraper] httpx got %d words from %s — below threshold, trying Playwright", word_count, url)
        text = await _fetch_playwright_text(url, max_chars)
        log.info("[scraper] Playwright got %d words from %s", len(text.split()), url)
    else:
        log.info("[scraper] httpx got %d words from %s", word_count, url)
    return text


async def fetch_all_links(portal_url: str) -> list[dict]:
    """Return all same-domain links from the listing page — no keyword filtering.
    Always uses Playwright so JS-rendered job links are included."""
    log.info("[scraper] fetching listing page with Playwright: %s", portal_url)
    html = await _fetch_playwright_html(portal_url)
    links = _extract_links(html, portal_url)
    log.info("[scraper] extracted %d candidate links from %s", len(links), portal_url)
    return links


def _extract_links(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    base_netloc = urlparse(base_url).netloc
    seen, links = set(), []

    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if urlparse(href).netloc != base_netloc or href in seen:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        seen.add(href)
        links.append({"url": href, "title": title[:120]})
        if len(links) >= 60:
            break

    return links


async def _fetch_raw_html(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        log.warning("[scraper] httpx failed for %s: %s", url, e)
        return ""


async def _fetch_httpx(url: str, max_chars: int) -> str:
    html = await _fetch_raw_html(url)
    return _extract_text(html, max_chars) if html else ""


async def _fetch_playwright_html(url: str) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        html = await page.content()
        await browser.close()
    return html


async def _fetch_playwright_text(url: str, max_chars: int) -> str:
    return _extract_text(await _fetch_playwright_html(url), max_chars)


def _extract_text(html: str, max_chars: int) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)[:max_chars]
