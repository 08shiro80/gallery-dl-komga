# -*- coding: utf-8 -*-

# Copyright 2026 gallery-dl-komga contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://klz9.com/"""

from .common import ChapterExtractor, MangaExtractor
from .. import exception
import hashlib
import time

BASE_PATTERN = r"(?:https?://)?(?:www\.)?klz9\.com"
_SECRET = "KL9K40zaSyC9K40vOMLLbEcepIFBhUKXwELqxlwTEF"


def _sign_headers():
    ts = str(int(time.time()))
    sig = hashlib.sha256((ts + "." + _SECRET).encode()).hexdigest()
    return {"x-client-ts": ts, "x-client-sig": sig}


def _parse_num(value):
    s = str(value).replace("-", ".")
    if "." in s:
        major, _, minor = s.partition(".")
        return (int(major) if major.isdigit() else 0), ("." + minor)
    return (int(s) if s.isdigit() else 0), ""


def _split_genres(value):
    return [g.strip() for g in (value or "").split(",") if g.strip()]


class Klz9Base():
    category = "klz9"
    root = "https://klz9.com"

    _manga_cache = {}

    def _api(self, path):
        return self.request(
            self.root + "/api" + path, headers=_sign_headers()).json()

    def _manga_data(self, slug):
        cache = Klz9Base._manga_cache
        if slug not in cache:
            cache[slug] = self._api("/manga/slug/" + slug)
        return cache[slug]

    def _manga_meta(self, data):
        return {
            "manga"      : data.get("name") or "",
            "manga_id"   : data.get("id"),
            "manga_slug" : data.get("slug") or "",
            "author"     : data.get("authors") or None,
            "artist"     : data.get("artists") or None,
            "description": (data.get("description") or "").strip() or None,
            "cover"      : data.get("cover") or None,
            "tags"       : _split_genres(data.get("genres")),
            "manga_alt"  : _split_genres(data.get("other_name")),
            "lang"       : "ja",
            "language"   : "Japanese",
        }


class Klz9ChapterExtractor(Klz9Base, ChapterExtractor):
    """Extractor for a single klz9 chapter"""
    directory_fmt = ("{category}", "{manga}", "c{chapter:>03}{chapter_minor}")
    filename_fmt  = "{page:>03}.{extension}"
    archive_fmt   = "{manga_id}_{chapter_id}_{page}"
    pattern       = BASE_PATTERN + r"/([^/?#]+)-chapter-(\d+(?:[.-]\d+)?)\.html"
    example       = "https://klz9.com/MANGA-chapter-1.html"

    def metadata(self, page):
        slug, chapter_num = self.groups
        data = self._manga_data(slug)
        meta = self._manga_meta(data)
        chapter, chapter_minor = _parse_num(chapter_num)

        target = chapter_num.replace("-", ".")
        self._chapter_id = None
        title = None
        date = None
        for ch in data.get("chapters", ()):
            if str(ch.get("chapter")) == target:
                self._chapter_id = ch.get("id")
                title = ch.get("name")
                date = ch.get("last_update")
                break
        if self._chapter_id is None:
            raise exception.NotFoundError("chapter")

        return {
            **meta,
            "chapter"      : chapter,
            "chapter_minor": chapter_minor,
            "chapter_id"   : self._chapter_id,
            "title"        : title,
            "date"         : date,
        }

    def images(self, page):
        data = self._api("/chapter/{}".format(self._chapter_id))
        content = data.get("content") or ""
        return [
            (line.strip(), None)
            for line in content.splitlines()
            if line.strip().startswith("http")
        ]


class Klz9MangaExtractor(Klz9Base, MangaExtractor):
    """Extractor for all chapters of a klz9 series"""
    chapterclass = Klz9ChapterExtractor
    pattern      = BASE_PATTERN + r"/(?!.+-chapter-\d)([^/?#]+)\.html"
    example      = "https://klz9.com/MANGA.html"

    def chapters(self, page):
        slug, = self.groups
        data = self._manga_data(slug)
        meta = self._manga_meta(data)
        manga_slug = data.get("slug") or slug

        result = []
        for ch in data.get("chapters", ()):
            chapter_num = str(ch.get("chapter"))
            chapter, chapter_minor = _parse_num(chapter_num)
            url = "{}/{}-chapter-{}.html".format(
                self.root, manga_slug, chapter_num)
            result.append((url, {
                **meta,
                "chapter"      : chapter,
                "chapter_minor": chapter_minor,
                "chapter_id"   : ch.get("id"),
                "title"        : ch.get("name"),
                "date"         : ch.get("last_update"),
            }))
        return result
