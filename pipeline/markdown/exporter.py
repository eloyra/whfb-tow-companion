"""
Markdown export stage: converts the raw scraped HTML into a markdown corpus
mirroring the wiki's URL structure.

Unlike the ``scraper/parsers/`` layer, which extracts the Contentful rich-text
JSON embedded in ``__NEXT_DATA__`` (painful to walk — see ADR-0006 and the
"known gaps" list in ``pipeline/CLAUDE.md``), this stage converts the
**rendered DOM** of each page. The site (tow.whfb.app) is statically generated
by Next.js: the full page body — prose, headings, lists, and stat tables — is
already server-rendered into the HTML on disk in ``data/raw/``. No headless
browser or re-crawl is needed.

Output: one ``.md`` file per page under ``data/markdown/``, at the path implied
by the page's URL (e.g. ``https://tow.whfb.app/special-rules/fear`` →
``data/markdown/special-rules/fear.md``), with a small YAML front-matter block
and internal links rewritten to relative sibling ``.md`` paths so the corpus is
self-contained and browsable offline.

This corpus serves three purposes: an offline copy of the wiki, a markdown-chunk
RAG baseline corpus (see ``docs/plans/baseline-showcase-graphrag.md``), and a
simpler future input for the parsers if the Contentful JSON approach is ever
replaced.

This stage is independent of ``parse``/``graph``/``embed``/``translate`` — it
only depends on ``data/raw/`` (the ``scrape`` stage) and does not touch the
Neo4j graph.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import markdownify as md
from tqdm import tqdm

from pipeline.scraper.parsers import _has_embedded_magic_items
from pipeline.scraper.utils import BASE_URL, canonicalize_url

logger = logging.getLogger(__name__)

_RAW_DIR = Path("data/raw")
_MANIFEST_PATH = _RAW_DIR / "manifest.json"
_MARKDOWN_DIR = Path("data/markdown")

# Tags that never carry corpus-relevant text — decomposed outright regardless
# of class (icon SVGs, action buttons).
_JUNK_TAGS: tuple[str, ...] = ("script", "style", "svg", "button")

# UI-chrome container classes observed on rendered pages (copy/report buttons,
# breadcrumbs, "Back / Source:" strip, PDF download links, tooltips) — none of
# these carry rules content. Verified by spot-checking one raw HTML file per
# page_type (army, unit, weapon, spell, magic_item, errata, terrain,
# troop_type, faq, core_rule) before writing this list.
_CHROME_CLASSES: tuple[str, ...] = (
    "minimal-source",
    "page-actions",
    "copy-note",
    "association-timestamp",
    "download-link",
    "breadcrumb__wrapper",
    "entry-nav",
    "main-actions",
    "cross-reference",
)

# Non-breaking spaces show up between a "Label:" <strong> and its value on
# unit/weapon/spell detail pages. Markdown has no use for them.
_NBSP = "\xa0"


class MarkdownExporter:
    """Converts every page in ``data/raw/manifest.json`` to a mirrored markdown file."""

    def run(self) -> None:
        manifest = self._load_manifest()
        known_paths = {self._url_to_path(r["url"]) for r in manifest}

        written = 0
        skipped = 0
        for record in tqdm(manifest, desc="Exporting markdown", unit="page"):
            try:
                if self._convert_page(record, known_paths):
                    written += 1
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001
                logger.warning("Failed to convert %s", record["url"], exc_info=True)
                skipped += 1

        logger.info("Markdown export complete: %d written, %d skipped", written, skipped)

    # ------------------------------------------------------------------
    # Manifest / path helpers
    # ------------------------------------------------------------------

    def _load_manifest(self) -> list[dict]:
        return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))

    def _url_to_path(self, url: str) -> str:
        """Return the URL path with no leading/trailing slash, e.g. ``"unit/abyssal-terror"``."""
        return urlparse(url).path.strip("/")

    def _html_path(self, record: dict) -> Path:
        # Normalise the manifest's stored path (may contain Windows backslashes)
        # rather than reconstructing it from the slug, since slug collisions
        # fall back to a different filename in the crawler (crawler.py:_save_html).
        return Path(record["html_path"].replace("\\", "/"))

    def _markdown_path(self, path: str) -> Path:
        return _MARKDOWN_DIR / f"{path}.md"

    # ------------------------------------------------------------------
    # Per-page conversion
    # ------------------------------------------------------------------

    def _convert_page(self, record: dict, known_paths: set[str]) -> bool:
        html_path = self._html_path(record)
        if not html_path.exists():
            logger.warning("Raw HTML missing for %s: %s", record["url"], html_path)
            return False

        html = html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        main = soup.select_one("main")
        if main is None:
            logger.warning("No <main> content region for %s — skipping", record["url"])
            return False

        title = self._extract_title(main)
        breadcrumb_meta = self._extract_breadcrumb_meta(main)
        self._mark_flavor_text(soup, main)
        self._strip_chrome(main)
        self._fix_adjacent_tags(main)
        current_path = self._url_to_path(record["url"])
        self._rewrite_links(main, current_path, known_paths)

        body = md(str(main), heading_style="ATX", bullets="-").replace(_NBSP, " ").strip()
        page_type = self._corrected_page_type(record, html)
        front_matter = self._front_matter(record, title, page_type, breadcrumb_meta)
        content = f"{front_matter}\n{body}\n"

        out_path = self._markdown_path(current_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return True

    def _extract_title(self, main: Tag) -> str | None:
        h1 = main.select_one("h1")
        if h1 is None:
            return None
        # Direct text only — the page's action buttons (copy/report) are
        # nested *inside* <h1 class="page-title"> on this site, so a plain
        # get_text() would pick up icon-button noise if it ever carried text.
        text = "".join(h1.find_all(string=True, recursive=False)).strip()
        return text or None

    def _extract_breadcrumb_meta(self, main: Tag) -> dict:
        """Pull structured metadata out of ``.breadcrumb__wrapper`` before it is stripped.

        Despite the name, this element is not pure navigation chrome: its first
        ``<ul>`` is the page's category/section path (e.g. ``["Gifts of Chaos",
        "Warriors of Chaos"]`` on a magic-item page), and its second ``<ul>``
        carries the wiki's own "Last update" date and a ``page-reference`` like
        ``"Ravening Hordes, p. 77"`` — the book/page source citation the graph
        schema already models as ``source_citation_book``/``source_citation_page``
        (ADR-0004/ADR-0005). Blanket-stripping this element as chrome (the
        original implementation) silently discarded it. Returns ``{}`` fields as
        ``None`` when the wrapper or a sub-part is absent (e.g. faq/errata pages).
        """
        wrapper = main.select_one(".breadcrumb__wrapper")
        result: dict = {
            "breadcrumb": [],
            "source_book": None,
            "source_page": None,
            "wiki_last_updated": None,
        }
        if wrapper is None:
            return result

        lists = wrapper.select("ul.breadcrumb")
        if lists:
            result["breadcrumb"] = [
                li.get_text(strip=True) for li in lists[0].select("li.breadcrumb-link")
            ]
        if len(lists) > 1:
            timestamp_li = lists[1].select_one("li.update-timestamp")
            if timestamp_li is not None:
                # separator=" ": get_text(strip=True) alone strips each text node
                # individually then joins with "", which eats the space around the
                # Next.js hydration <!-- --> comments splitting "Last update: " from
                # the date, producing "Last update:2024...".
                result["wiki_last_updated"] = (
                    timestamp_li.get_text(separator=" ", strip=True)
                    .removeprefix("Last update:")
                    .strip()
                )
            reference_li = lists[1].select_one("li.page-reference")
            if reference_li is not None:
                reference = reference_li.get_text(separator=" ", strip=True)
                # "Ravening Hordes, p. 77" / "Ravening Hordes, p. 38 & 108" — split
                # on the last ", p." so a book title containing a comma still works.
                if ", p." in reference:
                    book, _, page = reference.rpartition(", p.")
                    result["source_book"] = book.strip()
                    result["source_page"] = page.strip()
                else:
                    result["source_book"] = reference
        return result

    def _mark_flavor_text(self, soup: BeautifulSoup, main: Tag) -> None:
        """Wrap ``article.section-intro`` bodies in ``<em>`` so flavor text renders italic.

        The site distinguishes flavor/intro prose from rules text purely by
        this CSS class (verified: Acid Ichor's flavor sentence is wrapped in
        ``section-intro``, its rules sentence is a separate plain ``article``)
        — there is no inline ``<em>``/``<i>`` tag, so markdownify has no way to
        know a paragraph is flavor unless we mark it here, matching how the
        live site actually renders it (italic).

        Each paragraph gets its own ``<em>`` (joined by a single newline, not
        wrapped as one shared ``<em>`` around everything) — markdown emphasis
        cannot cross a blank line, so a multi-paragraph flavor block (3 of
        ~2,400 in this corpus) wrapped in one shared ``<em>`` would emit
        ``*Para one.\\n\\nPara two.*``, which most CommonMark renderers parse as
        two literal, un-italicised asterisks rather than emphasis. Per-paragraph
        wrapping costs a blank line between those paragraphs but keeps every
        emphasis span self-contained and valid.
        """
        for el in main.select(".section-intro"):
            children = list(el.contents)
            el.clear()
            for i, child in enumerate(children):
                if i > 0:
                    el.append(NavigableString("\n\n"))
                em = soup.new_tag("em")
                em.append(child)
                el.append(em)

    def _strip_chrome(self, main: Tag) -> None:
        for tag in main.select(",".join(_JUNK_TAGS)):
            tag.decompose()
        for cls in _CHROME_CLASSES:
            for el in main.select(f".{cls}"):
                el.decompose()

    def _fix_adjacent_tags(self, main: Tag) -> None:
        """Insert a space between sibling tags that have no text node between them.

        Several widgets on this site (special-rules/weapon "pill" lists, the
        magic-item name/type/cost header row, etc.) are laid out with CSS
        flex/gap spacing and carry no separating text node in the DOM at all.
        Left alone, markdown conversion glues them into one unreadable run
        (``[Fly](...)[Terror](...)`` or ``[Ogre Blade](...)(Magic Weapon)75
        points``). This is a generic structural fix — deliberately not scoped
        to one widget's class name, since new widget types keep surfacing
        this same pattern. Pairs that already have a text node between them
        (even just a comma) are left untouched.
        """
        for tag in main.find_all(True):
            if isinstance(tag.next_sibling, Tag):
                tag.insert_after(NavigableString(" "))

    def _rewrite_links(self, main: Tag, current_path: str, known_paths: set[str]) -> None:
        """Rewrite internal ``<a href>``s to relative sibling ``.md`` paths.

        - Links to a page present in this export (``known_paths``) become a
          relative path to the sibling markdown file, preserving any
          ``#fragment`` (used for in-page anchors like ``#special-rules``).
        - Links to the same host but outside the export (excluded page types
          like ``/sitemap/...``, or pages that failed to crawl) are rewritten
          to their absolute canonical URL, so the link still resolves online
          instead of pointing at a markdown file that doesn't exist.
        - External links, anchors (``#...``), and non-HTTP schemes
          (``mailto:``, ``javascript:``) are left untouched.
        """
        base_host = urlparse(BASE_URL).netloc.lower()
        current_dir = Path(current_path).parent

        for a in main.select("a[href]"):
            href = a["href"]
            if not href or href.startswith("#"):
                continue
            parsed = urlparse(href)
            if parsed.scheme and parsed.scheme not in ("http", "https"):
                continue  # mailto:, javascript:, tel:, ...

            # canonicalize_url() strips fragments (it's built for crawl-dedup,
            # not link rewriting), so capture the original fragment first.
            fragment = parsed.fragment
            canonical = canonicalize_url(href)
            canonical_parsed = urlparse(canonical)
            if canonical_parsed.netloc.lower() != base_host:
                continue  # external link — leave as-is

            target_path = canonical_parsed.path.strip("/")
            if target_path in known_paths:
                target_file = self._markdown_path(target_path)
                current_dir_abs = _MARKDOWN_DIR / current_dir
                rel = Path(os.path.relpath(target_file, start=current_dir_abs)).as_posix()
                if fragment:
                    rel = f"{rel}#{fragment}"
                a["href"] = rel
            else:
                a["href"] = canonical

    # ------------------------------------------------------------------
    # Front matter
    # ------------------------------------------------------------------

    def _corrected_page_type(self, record: dict, html: str) -> str:
        """Return the page_type, correcting the same manifest mislabels the parse
        stage already works around (ADR-0006 / ``parsers/__init__.py``).

        The crawler's manifest was written before ``classify_url`` grew its
        dedicated ``spell_page`` / distinct-``magic_item`` patterns, so a chunk
        of ``/spell/{slug}`` and ``/magic-item/{slug}`` pages are still stamped
        ``core_rule`` in ``data/raw/manifest.json``. The parse stage already
        detects and reroutes these (see the comments in
        ``parsers/__init__.py::run_all_parsers``); this mirrors that exact
        logic so front-matter ``page_type`` matches what the graph actually
        calls the page, rather than a stale manifest label.
        """
        page_type = record["page_type"]
        url_path = urlparse(record["url"]).path.rstrip("/")
        if page_type == "magic_item" and not _has_embedded_magic_items(html):
            return "core_rule"
        if page_type == "core_rule" and record["url"].rstrip("/").endswith("-army-list"):
            return "army_list"
        if page_type == "core_rule" and url_path.startswith("/spell/"):
            return "spell_page"
        if page_type == "core_rule" and url_path.startswith("/magic-item/"):
            return "magic_item"
        return page_type

    def _front_matter(
        self, record: dict, title: str | None, page_type: str, breadcrumb_meta: dict
    ) -> str:
        path = self._url_to_path(record["url"])
        slug = path.split("/")[-1] if path else record["url"]
        fields = {
            "url": record["url"],
            "page_type": page_type,
            "slug": slug,
            "title": title or slug,
            "fetched_at": record["fetched_at"],
            "breadcrumb": breadcrumb_meta["breadcrumb"],
            "source_book": breadcrumb_meta["source_book"],
            "source_page": breadcrumb_meta["source_page"],
            "wiki_last_updated": breadcrumb_meta["wiki_last_updated"],
        }
        lines = ["---"]
        for key, value in fields.items():
            lines.append(f"{key}: {self._yaml_value(value)}")
        lines.append("---")
        return "\n".join(lines) + "\n"

    def _yaml_value(self, value: str | list[str] | None) -> str:
        """Return *value* rendered as a single-line YAML scalar, list, or null."""
        if value is None:
            return "null"
        if isinstance(value, list):
            return "[" + ", ".join(self._yaml_scalar(v) for v in value) + "]"
        return self._yaml_scalar(value)

    def _yaml_scalar(self, value: str) -> str:
        """Return *value* quoted for safe YAML embedding if it needs it."""
        needs_quoting = any(c in value for c in ":#\"'[],") or value != value.strip() or value == ""
        if not needs_quoting:
            return value
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
