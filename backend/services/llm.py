import json
import logging
import os
import time
from typing import List, Dict

import anthropic

from backend.metrics import LLM_DURATION, LLM_TOKENS_INPUT, LLM_TOKENS_OUTPUT, LLM_ERRORS

from backend.services.scraper import fetch_page_text, fetch_all_links

log = logging.getLogger(__name__)

_client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

_JSON_ONLY = "Return ONLY valid JSON, no markdown, no explanation."


def _parse_json(raw: str) -> dict | list:
    text = raw.strip()
    if text.startswith("```"):
        # strip ```json ... ``` wrapper
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text.strip())

_ANALYZE_SYSTEM = (
    "You are a career advisor. Analyze a job description and evaluate fit with a candidate's CV. "
    + _JSON_ONLY
)


async def analyze_portals_stream(cv_url: str, portal_urls: List[str]):
    """Async generator — yields SSE event dicts for real-time progress."""
    yield {"type": "progress", "message": "Loading CV..."}
    cv_text = await fetch_page_text(cv_url, max_chars=4000)
    word_count = len(cv_text.split())
    if word_count < 20:
        yield {"type": "error", "message": "Could not read CV — make sure the URL is publicly accessible"}
        return
    yield {"type": "progress", "message": f"CV loaded ({word_count} words)"}
    yield {"type": "progress", "message": f"[CV TEXT]\n{cv_text[:500]}..."}

    for portal_url in portal_urls:
        yield {"type": "progress", "message": f"Scanning portal..."}

        all_links = await fetch_all_links(portal_url)
        yield {"type": "progress", "message": f"Found {len(all_links)} candidate links — filtering with LLM..."}
        for lnk in all_links:
            yield {"type": "progress", "message": f"  {lnk['url']}"}

        if all_links:
            job_links, prompt, raw = await _extract_job_links(all_links, portal_url)
            yield {"type": "progress", "message": f"[PROMPT - extract_job_links]\n{prompt}"}
            yield {"type": "progress", "message": f"[LLM RESPONSE - extract_job_links]\n{raw}"}
        else:
            job_links = []

        yield {"type": "progress", "message": f"Identified {len(job_links)} job pages"}

        if job_links:
            total = min(len(job_links), 15)
            for i, link in enumerate(job_links[:total]):
                yield {"type": "progress", "message": f"Analyzing {i + 1}/{total}: {link['title'][:60]}"}
                jd_text = await fetch_page_text(link["url"])
                yield {"type": "progress", "message": f"[JD TEXT - {link['url']}]\n{jd_text[:500]}..."}
                job, prompt, raw = await _analyze_single_jd(cv_text, link["title"], link["url"], jd_text)
                yield {"type": "progress", "message": f"[PROMPT - analyze_single_jd]\n{prompt[:600]}..."}
                yield {"type": "progress", "message": f"[LLM RESPONSE - analyze_single_jd]\n{raw}"}
                if job:
                    job["portal_url"] = portal_url
                    yield {"type": "job", "data": job}
                else:
                    yield {"type": "progress", "message": f"  skipped (could not parse LLM response)"}
        else:
            yield {"type": "progress", "message": "No job links found — analyzing listing page text directly..."}
            portal_text = await fetch_page_text(portal_url)
            jobs, prompt, raw = await _analyze_listing_fallback(cv_text, portal_url, portal_text)
            yield {"type": "progress", "message": f"[PROMPT - listing_fallback]\n{prompt[:600]}..."}
            yield {"type": "progress", "message": f"[LLM RESPONSE - listing_fallback]\n{raw}"}
            for job in jobs:
                job["portal_url"] = portal_url
                yield {"type": "job", "data": job}

    yield {"type": "done"}


async def analyze_portals(cv_url: str, portal_urls: List[str]) -> List[Dict]:
    cv_text = await fetch_page_text(cv_url, max_chars=4000)
    log.info("[llm] CV text: %d words", len(cv_text.split()))

    results = []
    for url in portal_urls:
        log.info("[llm] starting analysis for portal: %s", url)
        jobs = await _analyze_portal(cv_text, url)
        log.info("[llm] portal %s → %d jobs analyzed", url, len(jobs))
        results.append({"portal_url": url, "jobs": jobs})
    return results


async def _analyze_portal(cv_text: str, portal_url: str) -> List[Dict]:
    all_links = await fetch_all_links(portal_url)
    job_links, _, _ = await _extract_job_links(all_links, portal_url) if all_links else ([], "", "")
    log.info("[llm] LLM identified %d job links out of %d candidates", len(job_links), len(all_links))

    if job_links:
        jobs = []
        for i, link in enumerate(job_links[:15]):
            log.info("[llm] fetching JD %d/%d: %s", i + 1, min(len(job_links), 15), link["url"])
            jd_text = await fetch_page_text(link["url"])
            job, _, _ = await _analyze_single_jd(cv_text, link["title"], link["url"], jd_text)
            if job:
                log.info("[llm] analyzed: %s → fit_score=%s", job.get("title"), job.get("fit_score"))
                jobs.append(job)
            else:
                log.warning("[llm] failed to parse LLM response for %s", link["url"])
        return jobs

    log.info("[llm] no job links found, falling back to listing page text")
    portal_text = await fetch_page_text(portal_url)
    jobs, _, _ = await _analyze_listing_fallback(cv_text, portal_url, portal_text)
    return jobs


async def _extract_job_links(links: list[dict], portal_url: str) -> tuple[list[dict], str, str]:
    """Returns (job_links, prompt, raw_response)."""
    links_text = "\n".join(f"- [{l['title']}]({l['url']})" for l in links)

    prompt = f"""These links were extracted from a job portal listing page: {portal_url}

{links_text}

Which of these links lead to individual job position detail pages?
Exclude navigation, filters, login, and category pages.
Return JSON: {{"job_links": [{{"url": "...", "title": "..."}}]}}"""

    _t0 = time.perf_counter()
    try:
        msg = await _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_JSON_ONLY,
            messages=[{"role": "user", "content": prompt}],
        )
        LLM_DURATION.labels(model=msg.model, endpoint="extract_links").observe(time.perf_counter() - _t0)
        LLM_TOKENS_INPUT.labels(model=msg.model, endpoint="extract_links").inc(msg.usage.input_tokens)
        LLM_TOKENS_OUTPUT.labels(model=msg.model, endpoint="extract_links").inc(msg.usage.output_tokens)
    except Exception as _e:
        LLM_ERRORS.labels(endpoint="extract_links", error_type=type(_e).__name__).inc()
        raise
    raw = msg.content[0].text
    log.info("[llm] _extract_job_links raw response: %s", raw[:300])
    try:
        data = _parse_json(raw)
        return data.get("job_links", []), prompt, raw
    except json.JSONDecodeError as e:
        log.error("[llm] failed to parse job links JSON: %s | raw: %s", e, raw[:300])
        return [], prompt, raw


async def _analyze_single_jd(cv_text: str, title: str, url: str, jd_text: str) -> tuple[Dict | None, str, str]:
    """Returns (result, prompt, raw_response)."""
    if not jd_text.strip():
        log.warning("[llm] empty JD text for %s", url)
        return None, "", ""

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

    _t0 = time.perf_counter()
    try:
        msg = await _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_ANALYZE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        LLM_DURATION.labels(model=msg.model, endpoint="analyze_jd").observe(time.perf_counter() - _t0)
        LLM_TOKENS_INPUT.labels(model=msg.model, endpoint="analyze_jd").inc(msg.usage.input_tokens)
        LLM_TOKENS_OUTPUT.labels(model=msg.model, endpoint="analyze_jd").inc(msg.usage.output_tokens)
    except Exception as _e:
        LLM_ERRORS.labels(endpoint="analyze_jd", error_type=type(_e).__name__).inc()
        raise
    raw = msg.content[0].text
    try:
        return _parse_json(raw), prompt, raw
    except json.JSONDecodeError as e:
        log.error("[llm] failed to parse single JD JSON: %s | raw: %s", e, raw[:300])
        return None, prompt, raw


async def _analyze_listing_fallback(cv_text: str, portal_url: str, portal_text: str) -> tuple[List[Dict], str, str]:
    """Returns (jobs, prompt, raw_response)."""
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

    _t0 = time.perf_counter()
    try:
        msg = await _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_ANALYZE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        LLM_DURATION.labels(model=msg.model, endpoint="analyze_fallback").observe(time.perf_counter() - _t0)
        LLM_TOKENS_INPUT.labels(model=msg.model, endpoint="analyze_fallback").inc(msg.usage.input_tokens)
        LLM_TOKENS_OUTPUT.labels(model=msg.model, endpoint="analyze_fallback").inc(msg.usage.output_tokens)
    except Exception as _e:
        LLM_ERRORS.labels(endpoint="analyze_fallback", error_type=type(_e).__name__).inc()
        raise
    raw = msg.content[0].text
    try:
        data = _parse_json(raw)
        jobs = data.get("jobs", [])
        log.info("[llm] fallback extracted %d jobs from listing page", len(jobs))
        return jobs, prompt, raw
    except json.JSONDecodeError as e:
        log.error("[llm] failed to parse fallback JSON: %s | raw: %s", e, raw[:300])
        return [], prompt, raw
