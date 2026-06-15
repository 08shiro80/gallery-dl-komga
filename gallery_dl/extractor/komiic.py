# -*- coding: utf-8 -*-

# Copyright 2026 gallery-dl contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://komiic.com/ (Komiic / 漫画)"""

from .common import ChapterExtractor, MangaExtractor
from .. import text, exception

BASE_PATTERN = r"(?:https?://)?komiic\.com"
_API        = "https://komiic.com/api/query"

_GQL_COMIC = """
query comicById($comicId: ID!) {
  comicById(comicId: $comicId) {
    id title status year imageUrl
    authors   { id name }
    categories { id name }
  }
}
"""

_GQL_CHAPTERS = """
query chapterByComicId($comicId: ID!) {
  chaptersByComicId(comicId: $comicId) {
    id serial type dateUpdated size
  }
}
"""

_GQL_IMAGES = """
query imagesByChapterId($chapterId: ID!) {
  imagesByChapterId(chapterId: $chapterId) {
    id kid height width
  }
}
"""


def _parse_serial(serial):
    """Parse a chapter serial string like '1', '1.5' into (chapter_int, chapter_minor)."""
    s = str(serial)
    if "." in s:
        major, minor = s.split(".", 1)
        return (int(major) if major.isdigit() else 0), f".{minor}"
    return (int(s) if s.isdigit() else 0), ""


class KomiicBase():
    category = "komiic"
    root     = "https://komiic.com"

    def _gql(self, operation, query, variables):
        resp = self.request(
            _API,
            method="POST",
            headers={"Content-Type": "application/json"},
            json={"operationName": operation,
                  "query": query,
                  "variables": variables},
        ).json()
        if "errors" in resp:
            for err in resp["errors"]:
                self.log.warning("Komiic GraphQL error: %s", err.get("message", err))
        data = resp.get("data")
        if data is None:
            raise exception.StopExtraction(
                "Komiic API returned null data – possibly rate-limited"
            )
        return data

    def _comic_info(self, comic_id):
        data  = self._gql("comicById", _GQL_COMIC, {"comicId": comic_id})
        comic = data["comicById"]
        return {
            "manga"      : comic["title"],
            "manga_id"   : comic["id"],
            "author"     : [a["name"] for a in comic.get("authors", [])],
            "tags"       : [c["name"] for c in comic.get("categories", [])],
            "status"     : comic.get("status", ""),
            "year"       : comic.get("year", ""),
            "cover"      : comic.get("imageUrl", ""),
            "lang"       : "zh",
            "language"   : "Chinese",
        }

    def _chapter_list(self, comic_id):
        data = self._gql("chapterByComicId", _GQL_CHAPTERS, {"comicId": comic_id})
        return data["chaptersByComicId"]

    def _chapter_images(self, comic_id, chapter_id):
        data   = self._gql("imagesByChapterId", _GQL_IMAGES, {"chapterId": chapter_id})
        images = data["imagesByChapterId"]
        hdrs   = {"Referer": f"https://komiic.com/comic/{comic_id}/chapter/{chapter_id}/images/all"}

        def _rate_limit_retry(response):
            if response.status_code == 402:
                self.log.warning("Komiic rate limit (402) – sleeping 30s before retry")
                self.sleep(30, "ratelimit")
                return True
            return False

        return [
            (f"https://komiic.com/api/image/{img['kid']}"
             f"?mangaId={comic_id}&chapterId={chapter_id}",
             {"_http_headers": hdrs, "_http_retry": _rate_limit_retry})
            for img in images
        ]


class KomiicChapterExtractor(KomiicBase, ChapterExtractor):
    """Extractor for a single Komiic chapter"""
    directory_fmt = ("{category}", "{manga}", "{chapter_string}")
    filename_fmt  = "{page:>03}.{extension}"
    archive_fmt   = "{manga_id}_{chapter_id}_{page}"
    pattern       = BASE_PATTERN + r"/comic/(\d+)/chapter/(\d+)"
    example       = "https://komiic.com/comic/12345/chapter/67890/images/all"

    def metadata(self, page):
        comic_id, chapter_id = self.groups
        manga          = self._comic_info(comic_id)
        chapter_string = chapter_id
        chapter        = 0
        chapter_minor  = ""
        for ch in self._chapter_list(comic_id):
            if ch["id"] == chapter_id:
                prefix        = "Vol." if ch["type"] == "book" else "Ch."
                serial        = str(ch["serial"])
                chapter_string = f"{prefix}{serial}"
                chapter, chapter_minor = _parse_serial(serial)
                break
        self._comic_id   = comic_id
        self._chapter_id = chapter_id
        return {**manga, "chapter_string": chapter_string,
                "chapter_id": chapter_id,
                "chapter": chapter, "chapter_minor": chapter_minor}

    def images(self, page):
        del page
        return self._chapter_images(self._comic_id, self._chapter_id)


class KomiicMangaExtractor(KomiicBase, MangaExtractor):
    """Extractor for all chapters of a Komiic series"""
    chapterclass = KomiicChapterExtractor
    pattern      = BASE_PATTERN + r"/comic/(\d+)(?:/(?:[^/].*)?)?$"
    example      = "https://komiic.com/comic/12345"

    def chapters(self, page):
        comic_id, = self.groups
        manga  = self._comic_info(comic_id)
        result = []
        for ch in self._chapter_list(comic_id):
            prefix  = "Vol." if ch["type"] == "book" else "Ch."
            serial  = str(ch["serial"])
            ch_str  = f"{prefix}{serial}"
            chnum, chminor = _parse_serial(serial)
            url     = f"{self.root}/comic/{comic_id}/chapter/{ch['id']}/images/all"
            result.append((url, {
                **manga,
                "chapter_string": ch_str,
                "chapter_id"    : ch["id"],
                "chapter"       : chnum,
                "chapter_minor" : chminor,
                "date"          : ch.get("dateUpdated", ""),
                "count"         : ch.get("size", 0),
            }))
        return result
