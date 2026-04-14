"""
Web crawler for tow.whfb.app.

Strategy (ADR-0002):
- Dual-seed from the TOC (/), /sitemap/rules, and /sitemap/armies.
- Follow all internal <a href> links found on every fetched page.
- Deduplicate via a ``seen`` set (normalised URLs).
- Skip URLs excluded by robots.txt and external domains.
- Save each page's HTML to data/raw/{page_type}/{slug}.html.
- Write a manifest to data/raw/manifest.json mapping URL → file path + metadata.

ISR fallback handling (ADR-0002 addendum):
The site uses Next.js Incremental Static Regeneration.  Pages that haven't been
pre-rendered yet return ``isFallback: true`` in the ``__NEXT_DATA__`` blob with
empty ``pageProps``.  These pages are re-queued up to ``_MAX_ISR_RETRIES`` times
after a short delay.  The GET request itself triggers the ISR build; subsequent
requests return the full page.

Observability:
Every fetch outcome (success, 404, HTTP error, network failure, ISR retry,
ISR exhausted) is recorded in ``_failures`` and summarised in a structured log
block at the end of ``run()``.  The hardcoded army fallback, if triggered, is
logged at WARNING and each injected URL is listed explicitly.

Usage::

    from pipeline.scraper.crawler import Crawler
    Crawler().run()

Or via the pipeline entry point::

    python -m pipeline.run_pipeline --stage scrape
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from pipeline.scraper.utils import (
    BASE_URL,
    canonicalize_url,
    classify_url,
    fetch,
    is_crawlable,
    slug_from_url,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ISR fallback detection
# ---------------------------------------------------------------------------

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)

# Maximum number of retries for ISR fallback pages before giving up.
_MAX_ISR_RETRIES = 3
# Seconds to wait before retrying an ISR fallback page.
_ISR_RETRY_DELAY = 5.0


def _is_isr_fallback(html: str) -> bool:
    """Return True if the page is a Next.js ISR fallback (data not yet rendered)."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return False
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return False
    return bool(data.get("isFallback"))


# ---------------------------------------------------------------------------
# Fallback army slugs (ADR-0002: used only if TOC yields no army links)
# ---------------------------------------------------------------------------

_ARMY_SLUGS: list[str] = [
    "beastmen-brayherds",
    "chaos-dwarfs",
    "daemons-of-chaos",
    "dark-elves",
    "dwarfen-mountain-holds",
    "empire-of-man",
    "grand-cathay",
    "high-elf-realms",
    "kingdom-of-bretonnia",
    "lizardmen",
    "ogre-kingdoms",
    "orc-and-goblin-tribes",
    "realms-of-men",
    "regiments-of-renown",
    "skaven",
    "tomb-kings-of-khemri",
    "vampire-counts",
    "warriors-of-chaos",
    "wood-elf-realms",
]

# Page types that should be saved and re-parsed downstream.
# Seed-only types are fetched for link extraction only, not written to the manifest.
_SEED_ONLY_TYPES: frozenset[str] = frozenset({"toc", "sitemap", "army_reference"})

# Output directory
_RAW_DIR = Path("data/raw")


# ---------------------------------------------------------------------------
# Failure record
# ---------------------------------------------------------------------------

class _Failure:
    """Structured record for a single fetch failure."""

    __slots__ = ("url", "page_type", "reason", "status_code", "detail")

    def __init__(
        self,
        url: str,
        page_type: str,
        reason: str,
        status_code: int | None = None,
        detail: str = "",
    ) -> None:
        self.url = url
        self.page_type = page_type
        self.reason = reason          # "http_404" | "http_error" | "network" | "isr_exhausted"
        self.status_code = status_code
        self.detail = detail


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------

class Crawler:
    """Crawl tow.whfb.app and persist raw HTML for all content pages.

    After ``run()`` completes:
    - ``data/raw/{page_type}/{slug}.html`` contains each page's raw HTML.
    - ``data/raw/manifest.json`` is a list of records with keys:
      ``url``, ``page_type``, ``html_path``, ``fetched_at``.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._queue: deque[tuple[str, str]] = deque()
        self._manifest: list[dict] = []
        self._failures: list[_Failure] = []
        self._isr_retries: dict[str, int] = {}
        self._used_army_fallback: bool = False
        _RAW_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Seed the queue and crawl until it is empty, then write the manifest."""
        logger.info("Crawler starting — base URL: %s", BASE_URL)
        self._seed()

        total_attempts = 0
        while self._queue:
            url, page_type = self._queue.popleft()
            self._process(url, page_type)
            total_attempts += 1
            if total_attempts % 50 == 0:
                logger.info(
                    "Progress: %d attempts, %d saved, %d failures, %d queued",
                    total_attempts,
                    len(self._manifest),
                    len(self._failures),
                    len(self._queue),
                )

        self._write_manifest()
        self._log_summary(total_attempts)

    # ------------------------------------------------------------------
    # Seeding
    # ------------------------------------------------------------------

    def _seed(self) -> None:
        """Enqueue the three canonical seed URLs defined in ADR-0002."""
        seeds = [
            f"{BASE_URL}/",
            f"{BASE_URL}/sitemap/rules",
            f"{BASE_URL}/sitemap/armies",
        ]
        logger.info("Seeding crawler with %d entry points: %s", len(seeds), seeds)
        for url in seeds:
            self._enqueue(url)

    def _enqueue_army_fallbacks(self) -> None:
        """Enqueue hardcoded army slugs when TOC parsing yielded no army links.

        This is a safety net and should NOT fire during a normal crawl.
        If it does, the TOC page structure has likely changed.
        """
        self._used_army_fallback = True
        logger.warning(
            "FALLBACK TRIGGERED: TOC page yielded no /army/ links. "
            "The site's TOC structure may have changed. "
            "Injecting %d hardcoded army URLs as fallback:",
            len(_ARMY_SLUGS),
        )
        for slug in _ARMY_SLUGS:
            army_url = f"{BASE_URL}/army/{slug}"
            logger.warning("  [fallback] %s", army_url)
            self._enqueue(army_url)

    # ------------------------------------------------------------------
    # Core fetch-and-extract loop
    # ------------------------------------------------------------------

    def _process(self, url: str, page_type: str) -> None:
        """Fetch *url*, handle errors, detect ISR fallbacks, save, and extract links."""
        html = self._fetch_with_logging(url, page_type)
        if html is None:
            return  # failure already recorded

        # ISR fallback: page not yet pre-rendered by Next.js
        if page_type not in _SEED_ONLY_TYPES and _is_isr_fallback(html):
            retries = self._isr_retries.get(url, 0)
            if retries < _MAX_ISR_RETRIES:
                self._isr_retries[url] = retries + 1
                logger.info(
                    "ISR fallback [%s] — scheduling retry %d/%d in %.0fs",
                    url, retries + 1, _MAX_ISR_RETRIES, _ISR_RETRY_DELAY,
                )
                time.sleep(_ISR_RETRY_DELAY)
                self._queue.append((url, page_type))
            else:
                logger.error(
                    "ISR fallback [%s] — GAVE UP after %d retries; "
                    "page was never pre-rendered. This URL will be missing from the graph.",
                    url, _MAX_ISR_RETRIES,
                )
                self._failures.append(_Failure(
                    url=url,
                    page_type=page_type,
                    reason="isr_exhausted",
                    detail=f"isFallback=true after {_MAX_ISR_RETRIES} retries",
                ))
            return

        fetched_at = datetime.now(timezone.utc).isoformat()

        if page_type not in _SEED_ONLY_TYPES:
            html_path = self._save_html(html, url, page_type)
            self._manifest.append({
                "url": url,
                "page_type": page_type,
                "html_path": str(html_path),
                "fetched_at": fetched_at,
            })
            logger.debug("Saved [%s] %s → %s", page_type, url, html_path)

        # Extract outbound links and enqueue new ones
        soup = BeautifulSoup(html, "lxml")
        army_links_found = self._extract_links(soup, url, page_type)

        if page_type == "toc" and not army_links_found:
            self._enqueue_army_fallbacks()

    def _fetch_with_logging(self, url: str, page_type: str) -> str | None:
        """Fetch *url* and return HTML, or record a structured failure and return None."""
        try:
            return fetch(url)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 404:
                logger.warning(
                    "404 NOT FOUND [%s] %s — this URL does not exist on the wiki",
                    page_type, url,
                )
                self._failures.append(_Failure(
                    url=url, page_type=page_type,
                    reason="http_404", status_code=404,
                ))
            else:
                logger.error(
                    "HTTP %s [%s] %s — %s",
                    status, page_type, url, exc,
                )
                self._failures.append(_Failure(
                    url=url, page_type=page_type,
                    reason="http_error", status_code=status,
                    detail=str(exc),
                ))
            return None
        except requests.ConnectionError as exc:
            logger.error("CONNECTION ERROR [%s] %s — %s", page_type, url, exc)
            self._failures.append(_Failure(
                url=url, page_type=page_type,
                reason="network", detail=str(exc),
            ))
            return None
        except requests.Timeout:
            logger.error("TIMEOUT [%s] %s — request timed out after retries", page_type, url)
            self._failures.append(_Failure(
                url=url, page_type=page_type, reason="network", detail="timeout",
            ))
            return None
        except Exception as exc:
            logger.error("UNEXPECTED ERROR [%s] %s — %s", page_type, url, exc, exc_info=True)
            self._failures.append(_Failure(
                url=url, page_type=page_type, reason="unexpected", detail=str(exc),
            ))
            return None

    def _extract_links(self, soup: BeautifulSoup, base_url: str, page_type: str) -> bool:
        """Walk all <a href> elements and enqueue new internal content links.

        Returns True if at least one /army/ link was found (used by TOC fallback check).
        """
        army_found = False
        for tag in soup.find_all("a", href=True):
            href: str = tag["href"].strip()
            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue
            full_url = canonicalize_url(href, base=base_url)
            if full_url.lower().endswith(".pdf"):
                continue
            if not is_crawlable(full_url):
                continue
            link_type = classify_url(full_url)
            if link_type is None:
                continue
            if link_type == "army":
                army_found = True
            self._enqueue(full_url)
        return army_found

    # ------------------------------------------------------------------
    # URL queue management
    # ------------------------------------------------------------------

    def _enqueue(self, url: str) -> None:
        """Normalise *url* and add it to the queue if not already seen."""
        url = canonicalize_url(url)
        if url in self._seen:
            return
        page_type = classify_url(url)
        if page_type is None:
            return
        self._seen.add(url)
        self._queue.append((url, page_type))

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _save_html(self, html: str, url: str, page_type: str) -> Path:
        """Write *html* to ``data/raw/{page_type}/{slug}.html`` and return the path."""
        slug = slug_from_url(url)
        out_dir = _RAW_DIR / page_type
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / f"{slug}.html"
        if out_path.exists():
            # Slug collision: use full path segments to guarantee uniqueness
            path_segments = urlparse(url).path.strip("/").replace("/", "_")
            out_path = out_dir / f"{path_segments}.html"

        out_path.write_text(html, encoding="utf-8")
        return out_path

    def _write_manifest(self) -> None:
        """Serialise the manifest list to ``data/raw/manifest.json``."""
        manifest_path = _RAW_DIR / "manifest.json"
        manifest_path.write_text(
            json.dumps(self._manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Manifest written: %s (%d entries)", manifest_path, len(self._manifest))

    # ------------------------------------------------------------------
    # End-of-run summary
    # ------------------------------------------------------------------

    def _log_summary(self, total_attempts: int) -> None:
        """Emit a structured summary block after the crawl completes."""
        n_ok = len(self._manifest)
        n_fail = len(self._failures)

        # Group failures by reason
        by_reason: dict[str, list[_Failure]] = {}
        for f in self._failures:
            by_reason.setdefault(f.reason, []).append(f)

        logger.info("=" * 60)
        logger.info("CRAWL COMPLETE")
        logger.info("  Total fetch attempts : %d", total_attempts)
        logger.info("  Pages saved (OK)     : %d", n_ok)
        logger.info("  Failures             : %d", n_fail)

        if self._used_army_fallback:
            logger.warning(
                "  Army fallback used   : YES — TOC did not provide /army/ links; "
                "%d hardcoded URLs were injected. Investigate the TOC page structure.",
                len(_ARMY_SLUGS),
            )
        else:
            logger.info("  Army fallback used   : no (TOC provided army links organically)")

        isr_exhausted = by_reason.get("isr_exhausted", [])
        if isr_exhausted:
            logger.error(
                "  ISR exhausted        : %d page(s) never rendered after %d retries:",
                len(isr_exhausted), _MAX_ISR_RETRIES,
            )
            for f in isr_exhausted:
                logger.error("    [isr_exhausted] [%s] %s", f.page_type, f.url)

        not_found = by_reason.get("http_404", [])
        if not_found:
            logger.warning(
                "  404 Not Found        : %d URL(s) discovered organically but do not exist:",
                len(not_found),
            )
            for f in not_found:
                logger.warning("    [404] [%s] %s", f.page_type, f.url)

        http_errors = by_reason.get("http_error", [])
        if http_errors:
            logger.error(
                "  HTTP errors (non-404): %d URL(s):", len(http_errors),
            )
            for f in http_errors:
                logger.error(
                    "    [HTTP %s] [%s] %s — %s",
                    f.status_code, f.page_type, f.url, f.detail,
                )

        network_errors = by_reason.get("network", [])
        if network_errors:
            logger.error("  Network errors       : %d URL(s):", len(network_errors))
            for f in network_errors:
                logger.error("    [network] [%s] %s — %s", f.page_type, f.url, f.detail)

        unexpected = by_reason.get("unexpected", [])
        if unexpected:
            logger.error("  Unexpected errors    : %d URL(s):", len(unexpected))
            for f in unexpected:
                logger.error("    [unexpected] [%s] %s — %s", f.page_type, f.url, f.detail)

        if n_fail == 0:
            logger.info("  All pages fetched successfully.")
        logger.info("=" * 60)
