# -*- coding: utf-8 -*-

# Copyright 2026 gallery-dl-komga contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://cubari.moe/"""

from .common import Extractor, Message
from .. import text
import re

BASE_PATTERN = r"(?:https?://)?cubari\.moe/read/(\w+)/([^/?#]+)"

_CHAPTER_RE = re.compile(r"(\d+)(?:\.(\d+))?")


class CubariExtractor(Extractor):
    """Base class for cubari.moe"""
    category = "cubari"
    root = "https://cubari.moe"
    request_interval = (0.5, 1.5)

    def _series_info(self, source, slug):
        url = "{}/read/api/{}/series/{}/".format(self.root, source, slug)
        data = self.request(url).json()
        return {
            "manga"      : data.get("title") or slug,
            "manga_id"   : slug,
            "manga_url"  : "{}/read/{}/{}/".format(self.root, source, slug),
            "description": data.get("description") or "",
            "author"     : self._strip_unknown(data.get("author")),
            "artist"     : self._strip_unknown(data.get("artist")),
            "cover"      : data.get("cover") or None,
            "lang"       : "en",
        }, data

    @staticmethod
    def _strip_unknown(value):
        if not value or value == "Unknown":
            return None
        return value

    def _resolve_pages(self, groups):
        for value in groups.values():
            if isinstance(value, str):
                url = value if value.startswith("http") else self.root + value
                value = self.request(url).json()
            pages = []
            for item in value:
                if isinstance(item, dict):
                    src = item.get("src") or item.get("url")
                    if src:
                        pages.append(src)
                elif item:
                    pages.append(item)
            return pages
        return []

    def _chapter_date(self, chapter):
        ts = chapter.get("last_updated")
        if ts is None:
            return None
        return self.parse_timestamp(text.parse_int(ts))

    @staticmethod
    def _chapter_number(key):
        match = _CHAPTER_RE.match(key)
        if not match:
            return 0, ""
        minor = ("." + match.group(2)) if match.group(2) else ""
        return int(match.group(1)), minor


class CubariChapterExtractor(CubariExtractor):
    """Single chapter on cubari.moe"""
    subcategory = "chapter"
    directory_fmt = ("{category}", "{manga}",
                     "c{chapter:>03}{chapter_minor}")
    filename_fmt = "{manga}_c{chapter:>03}{chapter_minor}_{page:>03}.{extension}"
    archive_fmt = "{manga_id}_{chapter}_{chapter_minor}_{page}"
    pattern = BASE_PATTERN + r"/(\d[^/?#]*)"
    example = "https://cubari.moe/read/catbox/SLUG/1/1/"

    def _init(self):
        self.source, self.slug, self.chapter_key = self.groups

    def items(self):
        info, data = self._series_info(self.source, self.slug)
        chapter = data.get("chapters", {}).get(self.chapter_key)
        if not chapter:
            return
        chapter_num, minor = self._chapter_number(self.chapter_key)
        info.update({
            "title"        : chapter.get("title") or "",
            "chapter"      : chapter_num,
            "chapter_minor": minor,
            "chapter_id"   : self.chapter_key,
            "chapter_url"  : "{}/read/{}/{}/{}/".format(
                self.root, self.source, self.slug, self.chapter_key),
            "volume"       : text.parse_int(chapter.get("volume")),
            "date"         : self._chapter_date(chapter),
        })
        pages = self._resolve_pages(chapter.get("groups") or {})
        info["count"] = len(pages)
        yield Message.Directory, "", info
        for i, url in enumerate(pages, 1):
            yield Message.Url, url, text.nameext_from_url(
                url, {**info, "page": i})


class CubariMangaExtractor(CubariExtractor):
    """Full manga (all chapters) on cubari.moe"""
    subcategory = "manga"
    pattern = BASE_PATTERN + r"/?(?:[?#].*)?$"
    example = "https://cubari.moe/read/catbox/SLUG/"

    def _init(self):
        self.source, self.slug = self.groups

    def items(self):
        info, data = self._series_info(self.source, self.slug)
        chapters = data.get("chapters") or {}
        for key in sorted(chapters, key=lambda k: self._chapter_number(k)):
            chapter = chapters[key]
            chapter_num, minor = self._chapter_number(key)
            yield Message.Queue, "{}/read/{}/{}/{}/".format(
                self.root, self.source, self.slug, key), {
                    **info,
                    "title"        : chapter.get("title") or "",
                    "chapter"      : chapter_num,
                    "chapter_minor": minor,
                    "chapter_id"   : key,
                    "volume"       : text.parse_int(chapter.get("volume")),
                    "date"         : self._chapter_date(chapter),
                    "_extractor"   : CubariChapterExtractor,
                }
