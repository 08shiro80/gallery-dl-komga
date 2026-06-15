# -*- coding: utf-8 -*-

# Copyright 2026 gallery-dl contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://www.mangacopy.com/ (CopyManga / 拷貝漫畫)

No account required.  Content is fetched from the public web pages; the
chapter-list and page-list payloads are AES-128-CBC encrypted with keys
embedded in the surrounding HTML (var ccx / var ccy).

Requires the 'cryptography' package::

    pip install cryptography
"""

from .common import ChapterExtractor, MangaExtractor
import binascii
import json as _json
import re as _re


def _parse_chapter_str(s):
    m = _re.search(r'(\d+)(?:\.(\d+))?', str(s))
    if m:
        return int(m.group(1)), (f".{m.group(2)}" if m.group(2) else "")
    return 0, ""


def _decrypt(encrypted_text, key):
    """AES-128-CBC decrypt a CopyManga payload.

    Wire format: <16 ASCII bytes = raw IV> <hex-encoded ciphertext>
    The key is extracted from the page HTML and is exactly 16 ASCII chars.
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        raise ImportError(
            "CopyManga extractor requires the 'cryptography' package: "
            "pip install cryptography"
        )
    data       = encrypted_text.encode("latin-1")
    iv         = data[:16]
    ciphertext = binascii.unhexlify(data[16:])
    key_bytes  = key.encode("latin-1")[:16]
    cipher     = Cipher(algorithms.AES(key_bytes), modes.CBC(iv))
    dec        = cipher.decryptor()
    padded     = dec.update(ciphertext) + dec.finalize()
    pad_len    = padded[-1]
    return padded[:-pad_len].decode("utf-8").replace("\x00", "")


_DOMAIN_PAT = (
    r"(?:www\.)?"
    r"(?:copymanga\.(?:site|tv|com|org|info|net)"
    r"|mangacopy\.com"
    r"|copy20\.com"
    r"|2026copy\.com)"
)
BASE_PATTERN = r"(?:https?://)?" + _DOMAIN_PAT

_WWW_ROOT = "https://www.2026copy.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
}


class CopyMangaBase():
    """Base class for CopyManga extractors (unauthenticated web + AES decrypt)."""
    category = "copymanga"
    root     = _WWW_ROOT

    def _manga_page(self, path_word):
        return self.request(
            f"{_WWW_ROOT}/comic/{path_word}", headers=_HEADERS
        ).text

    def _extract_key(self, page):
        # Variable name changes across site versions (ccx, ccz, cct, …).
        # Match any single-letter variant; the value is always ≤32 ASCII chars.
        m = _re.search(r"var cc[a-z]\s*=\s*'([^']{1,32})'", page)
        if not m:
            raise Exception("CopyManga: AES key variable (var ccX) not found in page")
        return m.group(1)

    def _manga_info(self, path_word, page):
        # Primary: <h6 title="..."> inside comicParticulars-title-right
        t = _re.search(
            r'comicParticulars-title-right.*?<h6[^>]+title="([^"]+)"',
            page, _re.DOTALL,
        )
        title = t.group(1).strip() if t else ""
        if not title:
            # Fallback: og:title meta tag
            t = _re.search(r'property="og:title"\s+content="([^"]+)"', page)
            if t:
                title = t.group(1)
                for suffix in (" - 拷贝漫画", " - 拷貝漫畫", " - Copy漫畫", " - 拷漫"):
                    if suffix in title:
                        title = title.split(suffix, 1)[0].strip()
                        break

        if not title:
            title = path_word

        cover_m = _re.search(r'property="og:image"\s+content="([^"]+)"', page)
        cover   = cover_m.group(1) if cover_m else ""

        authors = _re.findall(r'href="/author/[^"]+"\s*>([^<]+)<', page)
        if not authors:
            authors = _re.findall(r'"author"\s*:\s*"([^"]+)"', page)

        return {
            "manga"    : title or path_word,
            "manga_id" : path_word,
            "author"   : [a.strip() for a in authors if a.strip()],
            "cover"    : cover,
            "lang"     : "zh",
            "language" : "Chinese",
        }

    def _chapter_list(self, path_word, ccx_key):
        """Fetch + decrypt the chapter list; return a flat list of chapter dicts.

        The endpoint requires a Referer pointing to the manga page to return
        the full chapter payload (without it the server returns an empty stub).
        Groups are at the top level of the decrypted JSON on current site versions.
        """
        url  = f"{_WWW_ROOT}/comicdetail/{path_word}/chapters"
        hdrs = {**_HEADERS, "Referer": f"{_WWW_ROOT}/comic/{path_word}", "dnts": "3"}
        data = self.request(url, headers=hdrs).json()
        enc  = data.get("results")
        if not enc or not isinstance(enc, str):
            return []
        obj = _json.loads(_decrypt(enc, ccx_key))
        # Full response: groups at top level; empty stub: groups inside build{}
        groups = obj.get("groups") or obj.get("build", {}).get("groups", {})
        group  = self.config("group") or "default"
        if group in groups:
            return groups[group].get("chapters", [])
        chapters = []
        for gdata in groups.values():
            chapters.extend(gdata.get("chapters", []))
        return chapters

    def _chapter_images(self, path_word, chapter_uuid):
        """Fetch the chapter page, extract cct key + contentKey, decrypt image list."""
        url  = f"{_WWW_ROOT}/comic/{path_word}/chapter/{chapter_uuid}"
        page = self.request(url, headers=_HEADERS).text
        key  = self._extract_key(page)
        # contentKey is a JS variable (not an HTML attribute) on current site versions
        m    = (_re.search(r"var contentKey\s*=\s*'([^']+)'", page)
                or _re.search(r'contentKey="([^"]+)"', page))
        if not m:
            raise Exception("CopyManga: contentKey not found in chapter page")
        images = _json.loads(_decrypt(m.group(1), key))
        if isinstance(images, list):
            return [img["url"] for img in images if img.get("url")]
        return []


class CopymangaChapterExtractor(CopyMangaBase, ChapterExtractor):
    """Extractor for a single CopyManga chapter"""
    directory_fmt = ("{category}", "{manga}", "{chapter_string}")
    filename_fmt  = "{page:>03}.{extension}"
    archive_fmt   = "{manga_id}_{chapter_id}_{page}"
    pattern       = BASE_PATTERN + r"/comic/([\w-]+)/chapter/([\w-]+)"
    example       = "https://www.2026copy.com/comic/MANGA/chapter/UUID"

    def metadata(self, page):
        path_word, chapter_uuid = self.groups
        manga_page     = self._manga_page(path_word)
        ccx_key        = self._extract_key(manga_page)
        manga          = self._manga_info(path_word, manga_page)
        chapter_string = chapter_uuid
        for ch in self._chapter_list(path_word, ccx_key):
            if ch.get("id") == chapter_uuid:
                chapter_string = ch.get("name", chapter_uuid)
                break
        chapter, chapter_minor = _parse_chapter_str(chapter_string)
        self._path_word    = path_word
        self._chapter_uuid = chapter_uuid
        return {
            **manga,
            "chapter_string": chapter_string,
            "chapter_id"    : chapter_uuid,
            "chapter"       : chapter,
            "chapter_minor" : chapter_minor,
        }

    def images(self, page):
        del page
        return [(url, None)
                for url in self._chapter_images(self._path_word, self._chapter_uuid)]


class CopymangaMangaExtractor(CopyMangaBase, MangaExtractor):
    """Extractor for all chapters of a CopyManga series"""
    chapterclass = CopymangaChapterExtractor
    pattern      = BASE_PATTERN + r"/comic/([\w-]+)/?(?:[?#].*)?$"
    example      = "https://www.2026copy.com/comic/MANGA"

    def initialize(self):
        super().initialize()
        self.page_url = f"{_WWW_ROOT}/comic/{self.groups[0]}"

    def chapters(self, page):
        path_word, = self.groups
        ccx_key = self._extract_key(page)
        manga   = self._manga_info(path_word, page)
        result  = []
        for ch in self._chapter_list(path_word, ccx_key):
            uuid = ch.get("id", "")
            name = ch.get("name", uuid)
            chapter, chapter_minor = _parse_chapter_str(name)
            result.append((f"{self.root}/comic/{path_word}/chapter/{uuid}", {
                **manga,
                "chapter_string": name,
                "chapter_id"    : uuid,
                "chapter"       : chapter,
                "chapter_minor" : chapter_minor,
            }))
        return result
