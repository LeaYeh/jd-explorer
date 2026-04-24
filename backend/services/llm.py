import anthropic
import json
import os
from typing import List, Dict
from backend.services.scraper import fetch_page_text

_client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

_SYSTEM = (
    "You are a career advisor. Analyze job listings from a job portal and evaluate "
    "fit with a candidate's CV. Return ONLY valid JSON, no markdown, no explanation."
)


async def analyze_portals(cv_url: str, portal_urls: List[str]) -> List[Dict]:
    cv_text = await fetch_page_text(cv_url, max_chars=4000)
    results = []
    for url in portal_urls:
        portal_text = await fetch_page_text(url)
        jobs = await _analyze_portal(cv_text, url, portal_text)
        results.append({"portal_url": url, "jobs": jobs})
    return results


async def _analyze_portal(cv_text: str, portal_url: str, portal_text: str) -> List[Dict]:
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
      "cv_adjustments": ["specific CV improvement 1", "..."],
      "skills_to_add": ["missing skill 1", "..."],
      "salary_range": "e.g. USD 120k-150k or N/A",
      "summary": "2-sentence fit summary"
    }}
  ]
}}

If no job listings found, return {{"jobs": []}}."""

    msg = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = json.loads(msg.content[0].text)
        return data.get("jobs", [])
    except (json.JSONDecodeError, IndexError):
        return []
