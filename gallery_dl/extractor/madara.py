# -*- coding: utf-8 -*-

# Copyright 2025 gallery-dl-komga contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Base extractor classes for sites using the Madara WordPress manga theme"""

from .common import Extractor, Message
from .. import text
import datetime
import re

# Chapter number from URL slug, e.g. "chapter-12", "chapter-12-5"
_CHAPTER_RE = re.compile(r"chapter-(\d+)(?:-(\d+))?", re.I)
# Lazy-loaded image attributes in priority order
_IMG_ATTRS = ("data-src", "data-lazy-src", "data-cfsrc", "src")
# WordPress human_time_diff() output, e.g. "13 hours ago", "1 day ago"
_RELATIVE_DATE_RE = re.compile(
    r"(\d+|an?|few)\s+(second|minute|hour|day|week|month|year)s?\s+ago",
    re.I,
)
_RELATIVE_UNIT_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,
    "year": 31536000,
}


_ABSOLUTE_DATE_FORMATS = (
    "%B %d, %Y",          # May 24, 2026
    "%b %d, %Y",          # May 24, 2026 (short month)
    "%d %B %Y",           # 24 May 2026
    "%d %b %Y",           # 24 May 2026 (short month)
    "%Y-%m-%dT%H:%M:%S",  # 2026-05-24T10:00:00
    "%Y-%m-%d %H:%M:%S",  # 2026-05-24 10:00:00
    "%Y-%m-%d",           # 2026-05-24
    "%d/%m/%Y",           # 24/05/2026
    "%m/%d/%Y",           # 05/24/2026 (US — only matches if first part > 12)
)


def _parse_date(value):
    """Parse a chapter-release-date string to a datetime.

    Accepts absolute forms (`May 24, 2026`, `2026-05-24`, ISO timestamps),
    WordPress relative forms (`13 hours ago`, `1 day ago`, `yesterday`,
    `today`, `just now`), and HTML `<time datetime="...">` attribute values.
    Returns None when the input cannot be matched.

    Re-used by non-Madara extractors (`mgeko`, `mgreadio`, ...) — keep the
    accepted input set tolerant."""
    value = value.strip().rstrip("Z").rstrip("+0000")
    for fmt in _ABSOLUTE_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            pass
    lower = value.lower()
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    if lower == "today" or lower == "just now":
        return now
    if lower == "yesterday":
        return now - datetime.timedelta(days=1)
    match = _RELATIVE_DATE_RE.search(lower)
    if match:
        amount_str, unit = match.group(1), match.group(2)
        amount = int(amount_str) if amount_str.isdigit() else 1
        return now - datetime.timedelta(
            seconds=amount * _RELATIVE_UNIT_SECONDS[unit])
    return None


_DATETIME_ATTR_RE = re.compile(r'datetime\s*=\s*["\']([^"\']+)["\']', re.I)
_TITLE_DATE_RE = re.compile(r'title\s*=\s*["\']([^"\']+)["\']', re.I)
_INLINE_DATE_RE = re.compile(
    r">\s*([A-Za-z]+ \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2}|"
    r"(?:\d+|an?|few)\s+(?:second|minute|hour|day|week|month|year)s?\s+ago|"
    r"yesterday|today|just now)\s*<",
    re.I,
)


def _extract_date_near(html_window):
    """Scan an HTML fragment for the first plausible release-date string.

    Looks at (in order): `<time datetime="...">`, `title="..."` attributes,
    inline text matching absolute or relative date forms. Returns a parsed
    datetime or None. Designed for chapter-listing-row HTML where the date
    sits either as an attribute or in a sibling `<span>`/`<em>`/`<time>`."""
    if not html_window:
        return None
    for regex in (_DATETIME_ATTR_RE, _TITLE_DATE_RE):
        match = regex.search(html_window)
        if match:
            parsed = _parse_date(match.group(1))
            if parsed is not None:
                return parsed
    match = _INLINE_DATE_RE.search(html_window)
    if match:
        return _parse_date(match.group(1))
    return None


def _img_url(tag):
    """Return the best image URL from an <img> tag string."""
    for attr in _IMG_ATTRS:
        url = text.extr(tag, attr + '="', '"').strip()
        if url and not url.startswith("data:"):
            return url
    srcset = text.extr(tag, 'srcset="', '"')
    if srcset:
        return srcset.strip().rsplit(",", 1)[-1].split()[0]
    return None


def _parse_chapter_slug(slug):
    """Return (chapter_int, chapter_minor_str) from a chapter URL slug."""
    m = _CHAPTER_RE.search(slug)
    if not m:
        return 0, ""
    major = int(m.group(1))
    minor = ("." + m.group(2)) if m.group(2) else ""
    return major, minor


def _labeled_content(page, label):
    """Return the summary-content HTML matching a summary-heading label, or ""."""
    m = re.search(
        r'summary-heading[^>]*>\s*<[^>]+>\s*' + re.escape(label) +
        r'\s*</[^>]+>\s*</div>\s*<div[^>]*class="summary-content[^"]*"[^>]*>'
        r"(.*?)</div>",
        page, re.I | re.S)
    return m.group(1) if m else ""


class MadaraExtractor(Extractor):
    """Base extractor for Madara WordPress manga sites"""
    basecategory = "madara"
    request_interval = (1.0, 2.0)

    # Override in subclasses
    # CSS-like description of where page images are found
    page_img_container = "reading-content"
    # Whether to always use the new /ajax/chapters/ endpoint
    use_new_chapter_endpoint = False

    def _manga_info(self, manga_url):
        page = self.request(manga_url).text

        title_block = (
            text.extr(page, 'class="post-title">', "</div>") or
            text.extr(page, 'id="manga-title">', "</h1>")
        )
        # prefer the <h1>; a sibling "HOT"/"NEW" badge span would leak into the title
        heading = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", title_block, re.S)
        title = text.remove_html(
            heading.group(1) if heading else title_block
        ).strip()

        author = text.remove_html(
            text.extr(page, 'class="author-content">', "</div>")
        ).strip()

        artist = text.remove_html(
            text.extr(page, 'class="artist-content">', "</div>")
        ).strip()

        summary = text.extr(page, 'class="summary__content', "</div>")
        if summary:
            summary = summary.partition(">")[2]
        else:
            summary = text.extr(page, 'class="post-content_item">', "</div>")
        description = text.remove_html(summary).strip()

        status = text.remove_html(
            _labeled_content(page, "Status") or
            text.extr(page, 'class="summary-content">', "</div>")
        ).strip()

        cover_block = text.extr(page, 'class="summary_image"', "</div>")
        cover = None
        for attr in _IMG_ATTRS:
            cover = text.extr(cover_block, attr + '="', '"').strip()
            if cover and not cover.startswith("data:"):
                break

        tags = re.findall(
            r'<a[^>]+>([^<]+)</a>',
            text.extr(page, 'class="genres-content">', "</div>"),
        ) + re.findall(
            r'<a[^>]+>([^<]+)</a>',
            text.extr(page, 'class="tags-content">', "</div>"),
        )

        manga_slug = manga_url.rstrip("/").rsplit("/", 1)[-1]

        return {
            "manga"      : title,
            "manga_id"   : manga_slug,
            "manga_url"  : manga_url,
            "author"     : author or None,
            "artist"     : artist or None,
            "description": description or None,
            "status"     : status or None,
            "cover"      : cover or None,
            "tags"       : tags,
            "lang"       : "en",
        }

    def _chapter_list(self, manga_url):
        """Return list of (chapter_url, chapter_title, date) newest-first."""
        manga_url_clean = manga_url.rstrip("/") + "/"

        if not self.use_new_chapter_endpoint:
            page = self.request(manga_url_clean).text
            chapters_html = text.extr(page, 'class="main version-chap', "</ul>")
            chapters = self._parse_chapter_list(chapters_html) if chapters_html \
                else []
            if chapters:
                return chapters

        # POST to /ajax/chapters/ (the list is often loaded lazily, so the
        # inline container above is empty and we fall back to this endpoint)
        try:
            response = self.request(
                manga_url_clean + "ajax/chapters/",
                method="POST",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            return self._parse_chapter_list(response.text)
        except Exception:
            return []

    def _parse_chapter_list(self, html):
        chapters = []
        for li in text.extract_iter(html, '<li class="wp-manga-chapter', "</li>"):
            url = text.extr(li, 'href="', '"')
            title = text.remove_html(text.extr(li, ">", "</a>")).strip()
            date = _parse_date(text.remove_html(
                text.extr(li, 'chapter-release-date', "</span>")).lstrip('">'))
            if url:
                chapters.append((url, title, date))
        return chapters

    _chapter_info_cache = {}

    def _chapter_info(self, manga_url, chapter_slug):
        """Return (chapter_url, date) for a chapter, using a per-manga cache so
        a single run resolves the chapter list (with dates) only once."""
        key = manga_url.rstrip("/")
        cache = MadaraExtractor._chapter_info_cache
        if key not in cache:
            mapping = {}
            for url, title, date in self._chapter_list(manga_url):
                slug = url.rstrip("/").rsplit("/", 1)[-1]
                mapping[slug] = (url, date)
            cache[key] = mapping
        return cache[key].get(chapter_slug, (None, None))

    def _chapter_images(self, chapter_url):
        """Return ordered list of image URLs for a chapter page."""
        page = self.request(chapter_url + "?style=list").text
        container = text.extr(page, 'class="' + self.page_img_container, "</div>")
        urls = []
        for tag in re.finditer(r"<img[^>]+>", container):
            url = _img_url(tag.group(0))
            if url:
                urls.append(url)
        return urls


class MadaraChapterExtractor(MadaraExtractor):
    """Generic chapter extractor for Madara sites"""
    subcategory = "chapter"
    directory_fmt = ("{category}", "{manga}",
                     "{volume:?v/ />02}c{chapter:>03}{chapter_minor}")
    filename_fmt = "{manga}_c{chapter:>03}{chapter_minor}_{page:>03}.{extension}"
    archive_fmt = "{manga_id}_{chapter}_{chapter_minor}_{page}"

    def _init(self):
        self._manga_slug = self.groups[0]
        self._chapter_slug = self.groups[1]

    def items(self):
        manga_url = "{}/manga/{}/".format(self.root, self._manga_slug)
        manga_info = self._manga_info(manga_url)
        chapter, minor = _parse_chapter_slug(self._chapter_slug)
        chapter_url, date = self._chapter_info(manga_url, self._chapter_slug)

        data = {
            **manga_info,
            "chapter"      : chapter,
            "chapter_minor": minor,
            "chapter_id"   : self._chapter_slug,
            "chapter_url"  : chapter_url or self.url,
            "date"         : date,
            "volume"       : 0,
        }

        images = self._chapter_images(self.url)
        yield Message.Directory, "", data
        for i, url in enumerate(images, 1):
            image_data = text.nameext_from_url(url, {**data, "page": i})
            yield Message.Url, url, image_data


class MadaraMangaExtractor(MadaraExtractor):
    """Generic manga extractor for Madara sites"""
    subcategory = "manga"

    def _init(self):
        self._manga_slug = self.groups[0]

    def items(self):
        manga_url = "{}/manga/{}/".format(self.root, self._manga_slug)
        manga_info = self._manga_info(manga_url)
        chapters = self._chapter_list(manga_url)

        for chapter_url, chapter_title, date in reversed(chapters):
            slug = chapter_url.rstrip("/").rsplit("/", 1)[-1]
            chapter, minor = _parse_chapter_slug(slug)
            data = {
                **manga_info,
                "chapter"      : chapter,
                "chapter_minor": minor,
                "chapter_id"   : slug,
                "chapter_title": chapter_title,
                "chapter_url"  : chapter_url,
                "date"         : date,
                "volume"       : 0,
                "_extractor"   : self.chapter_extractor,
            }
            yield Message.Queue, chapter_url, data
