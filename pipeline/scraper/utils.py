"""
Shared utilities for the scraper: HTTP session factory, rate-limited fetching,
URL canonicalisation, page-type classification, and slug extraction.

All configuration is read from environment variables (SCRAPE_BASE_URL,
SCRAPE_DELAY_SECONDS) or from pipeline/constants.py.  Nothing is hardcoded here.
"""

import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from pipeline.constants import WIKI_BASE_URL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (from env with sensible defaults)
# ---------------------------------------------------------------------------

BASE_URL: str = os.getenv("SCRAPE_BASE_URL", WIKI_BASE_URL).rstrip("/")
DELAY: float = float(os.getenv("SCRAPE_DELAY_SECONDS", "1.0"))
USER_AGENT: str = "WarhawmerTOW-GraphRAG-Thesis/1.0"

# Paths forbidden by robots.txt
_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "/api/",
    "/apps/",
    "/public/apps/",
    "/regenerate",
)

# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Return a singleton requests.Session with the project User-Agent set."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT})
    return _session


# ---------------------------------------------------------------------------
# Rate-limited, retry-enabled fetch
# ---------------------------------------------------------------------------

_last_request_time: float = 0.0


def _is_retryable(exc: BaseException) -> bool:
    """Return True if *exc* is a transient error worth retrying.

    4xx client errors (404 Not Found, 403 Forbidden, etc.) are permanent —
    retrying them wastes time and produces misleading logs.  Only 5xx server
    errors and network-level failures (connection reset, timeout) are retried.
    """
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500
    return True


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_is_retryable),
)
def fetch(url: str) -> str:
    """Fetch *url* and return its text body.

    Enforces a minimum delay of DELAY seconds between consecutive requests.
    Retries up to 3 times with exponential back-off for 5xx errors and
    network failures.  4xx client errors (e.g. 404) are raised immediately
    without retry.
    """
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < DELAY:
        time.sleep(DELAY - elapsed)

    logger.debug("GET %s", url)
    response = get_session().get(url, timeout=30)
    response.raise_for_status()
    _last_request_time = time.monotonic()
    return response.text


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def canonicalize_url(url: str, base: str = BASE_URL) -> str:
    """Resolve relative *url* against *base*, then normalise it.

    Normalisation:
    - Resolve relative paths (e.g. ``/unit/foo`` → full URL).
    - Strip URL fragment (``#...``).
    - Remove trailing slash from non-root paths.
    - Lowercase the scheme and host.
    """
    full = urljoin(base, url)
    parsed = urlparse(full)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalised = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        fragment="",
    )
    return urlunparse(normalised)


def is_crawlable(url: str) -> bool:
    """Return True if *url* should be enqueued for crawling.

    Excluded:
    - External domains (anything not under BASE_URL's host).
    - Paths forbidden by robots.txt (_EXCLUDED_PREFIXES).
    - Non-HTTP(S) schemes (mailto:, javascript:, …).
    """
    parsed = urlparse(url)
    base_host = urlparse(BASE_URL).netloc.lower()

    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc.lower() != base_host:
        return False
    for prefix in _EXCLUDED_PREFIXES:
        if parsed.path.startswith(prefix):
            return False
    return True


def slug_from_url(url: str) -> str:
    """Extract the last path segment of *url* to use as a node/file slug.

    Examples::

        https://tow.whfb.app/unit/blood-knights  →  blood-knights
        https://tow.whfb.app/army/skaven          →  skaven
        https://tow.whfb.app/                     →  toc
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return "toc"
    return path.split("/")[-1]


# ---------------------------------------------------------------------------
# Page-type classification
# ---------------------------------------------------------------------------

# Ordered list of (compiled regex, page_type) pairs.
# The FIRST match wins, so more-specific patterns must come first.
_PAGE_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/?$"), "toc"),
    (re.compile(r"^/sitemap(/.*)?$"), "sitemap"),
    (re.compile(r"^/army/[^/]+/reference/?$"), "army_reference"),
    (re.compile(r"^/army/[^/]+$"), "army"),
    (re.compile(r"^/unit/[^/]+$"), "unit"),
    (re.compile(r"^/faq/?$"), "faq"),
    (re.compile(r"^/faq/[^/]+$"), "faq"),
    (re.compile(r"^/errata/?$"), "errata"),
    (re.compile(r"^/special-rules/[^/]+$"), "special_rule"),
    (re.compile(r"^/troop-types-in-detail/[^/]+$"), "troop_type"),
    (re.compile(r"^/magic-items/[^/]+$"), "magic_item"),
    (re.compile(r"^/the-lores-of-magic/[^/]+$"), "spell"),
    (re.compile(r"^/weapons-of-war/[^/]+$"), "weapon"),
    # Generic two-segment path: /{section}/{slug} — core rulebook pages.
    (re.compile(r"^/[^/]+/[^/]+$"), "core_rule"),
]


def classify_url(url: str) -> str | None:
    """Return the page type for *url*, or None if the URL should be skipped.

    Page types correspond directly to parser classes and output node types.
    Returns None for URLs that carry no parseable content (e.g. bare domain root
    that doesn't match TOC pattern, PDF links, etc.).
    """
    path = urlparse(url).path
    for pattern, page_type in _PAGE_TYPE_PATTERNS:
        if pattern.match(path):
            return page_type
    return None
