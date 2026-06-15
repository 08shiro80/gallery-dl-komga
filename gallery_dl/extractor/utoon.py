# -*- coding: utf-8 -*-

# Copyright 2026 gallery-dl-komga contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://utoon.net/"""

from .mangaclash import MangaclashExtractor
from .madara import MadaraChapterExtractor, MadaraMangaExtractor

BASE_PATTERN = r"(?:https?://)?(?:www\.)?utoon\.net"


class UtoonExtractor(MangaclashExtractor):
    category = "utoon"
    root = "https://utoon.net"
    use_new_chapter_endpoint = True


class UtoonChapterExtractor(UtoonExtractor, MadaraChapterExtractor):
    pattern = BASE_PATTERN + r"/manga/([^/?#]+)/(chapter-[^/?#]+)"
    example = "https://utoon.net/manga/MANGA/chapter-1/"


class UtoonMangaExtractor(UtoonExtractor, MadaraMangaExtractor):
    pattern = BASE_PATTERN + r"/manga/([^/?#]+)/?(?:[?#].*)?$"
    example = "https://utoon.net/manga/MANGA/"
    chapter_extractor = UtoonChapterExtractor
