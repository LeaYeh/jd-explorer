import anthropic
import json
import os
from typing import List, Dict
from backend.services.scraper import fetch_page_text, fetch_all_links

_client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

_JSON_ONLY = "Return ONLY valid JSON, no markdown, no explanation."

_ANALYZE_SYSTEM = (
    "You are a career advisor. Analyze a job description and evaluate fit with a candidate's CV. "
    + _JSON_ONLY
)


async def analyze_portals(cv_url: str, portal_urls: List[str]) -> List[Dict]:
    cv_text = await fetch_page_text(cv_url, max_chars=4000)
    results = []
    for url in portal_urls:
        jobs = await _analyze_portal(cv_text, url)
        results.append({"portal_url": url, "jobs": jobs})
    return results


async def _analyze_portal(cv_text: str, portal_url: str) -> List[Dict]:
    # Phase 1: collect all same-domain links, let LLM decide which are job pages
    all_links = await fetch_all_links(portal_url)
    job_links = await _extract_job_links(all_links, portal_url) if all_links else []

    if job_links:
        # Phase 2: fetch + analyze each job detail page
        jobs = []
        for link in job_links[:15]:
            jd_text = await fetch_page_text(link["url"])
            job = await _analyze_single_jd(cv_text, link["title"], link["url"], jd_text)
            if job:
                jobs.append(job)
        return jobs

    # Fallback: no navigable job links, analyze listing page text directly
    portal_text = await fetch_page_text(portal_url)
    return await _analyze_listing_fallback(cv_text, portal_url, portal_text)


async def _extract_job_links(links: list[dict], portal_url: str) -> list[dict]:
    """Ask LLM to identify which links are individual job detail pages."""
    links_text = "\n".join(f"- [{l['title']}]({l['url']})" for l in links)

    prompt = f"""These links were extracted from a job portal listing page: {portal_url}

{links_text}

Which of these links lead to individual job position detail pages?
Exclude navigation, filters, login, and category pages.
Return JSON: {{"job_links": [{{"url": "...", "title": "..."}}]}}"""

    msg = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_JSON_ONLY,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text
    try:
        data = json.loads(raw)
        return data.get("job_links", [])
    except (json.JSONDecodeError, IndexError):
        return []


async def _analyze_single_jd(cv_text: str, title: str, url: str, jd_text: str) -> Dict | None:
    if not jd_text.strip():
        return None

    prompt = f"""CV:
{cv_text}

Job Title: {title}
Job URL: {url}
Job Description:
{jd_text}

Return JSON:
{{
  "title": "string",
  "fit_score": 0-100,
  "cv_adjustments": ["specific CV improvement 1", "..."],
  "skills_to_add": ["missing skill 1", "..."],
  "salary_range": "e.g. USD 120k-150k or N/A",
  "summary": "2-sentence fit summary"
}}"""

    msg = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_ANALYZE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return json.loads(msg.content[0].text)
    except (json.JSONDecodeError, IndexError):
        return None


async def _analyze_listing_fallback(cv_text: str, portal_url: str, portal_text: str) -> List[Dict]:
    prompt = f"""CV:
{cv_text}

Job Portal: {portal_url}
Portal Content:
{portal_text}

Extract all job listings and analyze each against the CV. Return JSON:
{{
  "jobs": [
    {{
      "title": "string",
      "fit_score": 0-100,
      "cv_adjustments": ["..."],
      "skills_to_add": ["..."],
      "salary_range": "string or N/A",
      "summary": "2-sentence fit summary"
    }}
  ]
}}
If no listings found, return {{"jobs": []}}."""

    msg = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_ANALYZE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = json.loads(msg.content[0].text)
        return data.get("jobs", [])
    except (json.JSONDecodeError, IndexError):
        return []
