import httpx
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JD-Explorer/1.0)"}
# Threshold: if httpx gets fewer than this many words, the page is likely JS-rendered
_JS_THRESHOLD = 80


async def fetch_page_text(url: str, max_chars: int = 8000) -> str:
    text = await _fetch_httpx(url, max_chars)
    if len(text.split()) < _JS_THRESHOLD:
        text = await _fetch_playwright(url, max_chars)
    return text


async def _fetch_httpx(url: str, max_chars: int) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
        return _extract_text(resp.text, max_chars)
    except Exception:
        return ""


async def _fetch_playwright(url: str, max_chars: int) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        html = await page.content()
        await browser.close()

    return _extract_text(html, max_chars)


def _extract_text(html: str, max_chars: int) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:max_chars]
