import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JD-Explorer/1.0)"}
_JS_THRESHOLD = 100


async def fetch_page_text(url: str, max_chars: int = 8000) -> str:
    text = await _fetch_httpx(url, max_chars)
    if len(text.split()) < _JS_THRESHOLD:
        text = await _fetch_playwright_text(url, max_chars)
    return text


async def fetch_all_links(portal_url: str) -> list[dict]:
    """Return all same-domain links from the listing page — no keyword filtering."""
    html = await _fetch_raw_html(portal_url)
    if len(html.split()) < _JS_THRESHOLD:
        html = await _fetch_playwright_html(portal_url)
    return _extract_links(html, portal_url)


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
        if len(links) >= 60:  # cap before passing to LLM
            break

    return links


async def _fetch_raw_html(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            return resp.text
    except Exception:
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
