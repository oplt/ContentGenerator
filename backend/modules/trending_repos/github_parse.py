"""HTML parsing helpers for GitHub trending pages."""

from __future__ import annotations

import hashlib
import re
from typing import Any

STAR_GAIN_PATTERN = re.compile(
    r"([\d.,]+[kmb]?)\s+stars?\s+(today|this week|this month)", re.IGNORECASE
)
REPO_ID_PATTERN = re.compile(r'"repository_id":\s*(\d+)')


def parse_trending_repo(article: Any) -> dict[str, Any] | None:
    link = article.select_one("h2 a[href]")
    full_name = extract_repo_name(link)
    if not full_name:
        return None

    description_el = article.select_one("p")
    language_el = article.select_one('[itemprop="programmingLanguage"]')
    stars_el = article.select_one(f'a[href="/{full_name}/stargazers"]')
    forks_el = article.select_one(f'a[href="/{full_name}/forks"]')
    article_text = article.get_text(" ", strip=True)

    stars_count = parse_count(stars_el.get_text(" ", strip=True) if stars_el else "")
    forks_count = parse_count(forks_el.get_text(" ", strip=True) if forks_el else "")
    stars_gained = extract_stars_gained(article_text)
    github_id = extract_repo_id(str(article)) or stable_repo_id(full_name)

    return {
        "github_id": github_id,
        "name": full_name,
        "full_name": full_name,
        "description": description_el.get_text(" ", strip=True) or None if description_el else None,
        "html_url": f"https://github.com/{full_name}",
        "language": language_el.get_text(" ", strip=True) or None if language_el else None,
        "topics": [],
        "stars_count": stars_count,
        "forks_count": forks_count,
        "watchers_count": stars_count,
        "open_issues_count": 0,
        "stars_gained": stars_gained,
    }


def extract_repo_name(link: Any) -> str | None:
    href = (link.get("href") if link else "") or ""
    full_name = href.strip().strip("/")
    if not full_name or "/" not in full_name:
        return None
    owner, repo = full_name.split("/", 1)
    return f"{owner.strip()}/{repo.strip()}"


def extract_repo_id(article_html: str) -> int:
    match = REPO_ID_PATTERN.search(article_html)
    return int(match.group(1)) if match else 0


def extract_stars_gained(article_text: str) -> int:
    match = STAR_GAIN_PATTERN.search(article_text)
    if not match:
        return 0
    return parse_count(match.group(1))


def parse_count(raw: str) -> int:
    cleaned = raw.strip().lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)([kmb]?)", cleaned)
    if not match:
        return 0

    value = float(match.group(1))
    multiplier = {
        "": 1,
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
    }[match.group(2)]
    return int(value * multiplier)


def stable_repo_id(full_name: str) -> int:
    # GitHub Trending markup does not consistently expose a repo id. Use a
    # deterministic fallback so snapshots remain stable when API enrichment is off.
    return int(hashlib.sha1(full_name.encode("utf-8")).hexdigest()[:12], 16)


# Historical private-name aliases kept for compatibility re-exports.
_parse_trending_repo = parse_trending_repo
_extract_repo_name = extract_repo_name
_extract_repo_id = extract_repo_id
_extract_stars_gained = extract_stars_gained
_parse_count = parse_count
_stable_repo_id = stable_repo_id
