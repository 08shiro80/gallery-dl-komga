# -*- coding: utf-8 -*-

# Copyright 2026 gallery-dl contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://www.dm5.com/ (DM5 / 动漫屋)"""

from .common import ChapterExtractor, MangaExtractor
from .. import text
import re as _re


def _parse_chapter_str(s):
    """Extract (chapter, chapter_minor) from a free-form Chinese chapter label.

    '第001话' → (1, ''),  '第1.5话' → (1, '.5'),  '番外' → (0, '')
    """
    m = _re.search(r'(\d+)(?:\.(\d+))?', str(s))
    if m:
        return int(m.group(1)), (f".{m.group(2)}" if m.group(2) else "")
    return 0, ""


BASE_PATTERN = r"(?:https?://)?(?:www\.)?dm5\.(?:com|cn)"
_BASE_URL    = "https://www.dm5.com"
_HEADERS     = {
    "User-Agent"     : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW",
}


class Dm5Base():
    category = "dm5"
    root     = _BASE_URL

    def _unpack_js(self, js):
        """Decode Dean Edwards p,a,c,k,e,r packed JavaScript."""
        # Use (?:[^'\\]|\\.)* so escaped \' inside the packed string doesn't break the match
        m = _re.search(r"\('((?:[^'\\]|\\.)*)',(\d+),(\d+),'([^']+)'", js)
        if not m:
            return js
        p, a, c = m.group(1).replace("\\'", "'"), int(m.group(2)), int(m.group(3))
        k = m.group(4).split("|")
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"

        def decode(n):
            s = ""
            while n > 0:
                r = n % a
                s = (chr(r + 29) if r > 35 else chars[r]) + s
                n //= a
            return s or "0"

        lookup = {decode(i): (k[i] if i < len(k) and k[i] else decode(i))
                  for i in range(c)}
        return _re.sub(r"\b\w+\b", lambda mo: lookup.get(mo.group(), mo.group()), p)

    def _chapter_images(self, chapter_url, cid, mid, dt, sign, count):
        hdrs = {**_HEADERS, "Referer": chapter_url}
        images = []
        page = 1
        while len(images) < count:
            prev_len = len(images)
            api_url = (
                f"{chapter_url}chapterfun.ashx"
                f"?cid={cid}&page={page}&key=&language=1&gtk=6"
                f"&_cid={cid}&_mid={mid}&_dt={dt}&_sign={sign}"
            )
            js      = self.request(api_url, headers=hdrs).text
            unpacked = self._unpack_js(js)
            img_hdrs = {"Referer": f"{_BASE_URL}/m{cid}/"}

            # New API format: pix (CDN base URL) + pvalue (relative image paths)
            pix_m = _re.search(r'var\s+pix\s*=\s*"(https://[^"]+)"', unpacked)
            pvalue_items = _re.findall(r'"(/[^"]+\.(?:jpg|png|webp|gif))"', unpacked)
            key_m = _re.search(r"var\s+key\s*=\s*['\"]([^'\"]+)['\"]", unpacked)
            if pix_m and pvalue_items:
                pix = pix_m.group(1).rstrip("/")
                key = key_m.group(1) if key_m else ""
                for path in pvalue_items:
                    url = f"{pix}/{path.lstrip('/')}?cid={cid}&key={key}"
                    images.append((url, {"_http_headers": img_hdrs}))
                    if len(images) >= count:
                        break
            else:
                # Fallback: old format with full https image URLs in the unpacked JS
                for url in _re.findall(r'"(https://[^"]+\.(?:jpg|png|webp|gif)[^"]*)"', unpacked):
                    images.append((url, {"_http_headers": img_hdrs}))
                    if len(images) >= count:
                        break

            if len(images) == prev_len:
                break  # no progress — API not returning parseable image URLs
            page += 2
        return images


class Dm5ChapterExtractor(Dm5Base, ChapterExtractor):
    """Extractor for a single DM5 chapter"""
    directory_fmt = ("{category}", "{manga}", "{chapter_string}")
    filename_fmt  = "{page:>03}.{extension}"
    archive_fmt   = "{manga_id}_{chapter_id}_{page}"
    pattern       = BASE_PATTERN + r"/(m\d+)/?"
    example       = "https://www.dm5.com/m12345/"

    def initialize(self):
        super().initialize()
        slug          = self.groups[0]
        self.page_url = f"{_BASE_URL}/{slug}/"

    def metadata(self, page):
        def _var(name):
            m = _re.search(rf'var {name}\s*=\s*"?([^";\n]+)"?', page)
            return m.group(1).strip().strip('"') if m else ""

        self._cid   = _var("DM5_CID")
        self._mid   = _var("DM5_MID")
        self._dt    = _var("DM5_VIEWSIGN_DT")
        self._sign  = _var("DM5_VIEWSIGN")
        self._count = int(_var("DM5_IMAGE_COUNT") or "0")

        ctitle = _var("DM5_CTITLE")
        if " " in ctitle:
            manga, _, chapter_string = ctitle.partition(" ")
        else:
            manga = text.unescape(_re.sub(r"漫画$", "", _re.search(
                r"<title>([^_<]+)", page).group(1).strip()) if _re.search(
                r"<title>([^_<]+)", page) else "")
            chapter_string = ctitle

        chapter, chapter_minor = _parse_chapter_str(chapter_string)
        return {
            "manga"         : manga,
            "manga_id"      : self._mid,
            "chapter_string": chapter_string,
            "chapter_id"    : self._cid,
            "chapter"       : chapter,
            "chapter_minor" : chapter_minor,
            "lang"          : "zh",
            "language"      : "Chinese",
        }

    def images(self, page):
        return self._chapter_images(
            self.page_url, self._cid, self._mid, self._dt, self._sign, self._count,
        )


class Dm5MangaExtractor(Dm5Base, MangaExtractor):
    """Extractor for all chapters of a DM5 series"""
    chapterclass = Dm5ChapterExtractor
    pattern      = BASE_PATTERN + r"/manhua-([^/?#]+)/?"
    example      = "https://www.dm5.com/manhua-TITLE/"

    def initialize(self):
        super().initialize()
        self.page_url = f"{_BASE_URL}/manhua-{self.groups[0]}/"

    def chapters(self, page):
        # Title: strip trailing "漫画" suffix from page title
        title_m = _re.search(r"<title>([^_<]+)", page)
        manga   = _re.sub(r"漫画$", "", title_m.group(1).strip()) if title_m else ""

        manga_id_m = _re.search(r"var DM5_MID\s*=\s*(\d+)", page)
        manga_id   = manga_id_m.group(1) if manga_id_m else ""

        result = []
        for ul_m in _re.finditer(
            r'<ul[^>]+id="detail-list-select-\d+"[^>]*>(.*?)</ul>', page, _re.DOTALL
        ):
            for a_m in _re.finditer(
                r'href="(/m(\d+)/)"[^>]*>([^<]+)', ul_m.group(1)
            ):
                href, cid, title = a_m.group(1), a_m.group(2), a_m.group(3).strip()
                url = _BASE_URL + href
                chapter, chapter_minor = _parse_chapter_str(title)
                result.append((url, {
                    "manga"         : manga,
                    "manga_id"      : manga_id,
                    "chapter_string": title,
                    "chapter_id"    : cid,
                    "chapter"       : chapter,
                    "chapter_minor" : chapter_minor,
                    "lang"          : "zh",
                    "language"      : "Chinese",
                }))
        result.reverse()
        return result
