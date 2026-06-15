# -*- coding: utf-8 -*-

# Copyright 2026 gallery-dl contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Unscramble GigaViewer (Young Jump / tonarinoyj) block-transposed images."""

import math
from .common import PostProcessor

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

_DIVIDE = 4   # 4×4 grid
_MULT   = 8   # block size alignment factor


def _unscramble(path):
    img = Image.open(path)
    w, h = img.size

    bw = math.floor(w / (_DIVIDE * _MULT)) * _MULT
    bh = math.floor(h / (_DIVIDE * _MULT)) * _MULT

    # Each block at (src_row, src_col) moves to (src_col, src_row) — a transpose.
    # Remainder pixels outside the aligned grid are left in place.
    result = img.copy()
    for e in range(_DIVIDE * _DIVIDE):
        src_col, src_row = e % _DIVIDE, e // _DIVIDE
        dst_col, dst_row = src_row, src_col   # transpose
        sx, sy = src_col * bw, src_row * bh
        dx, dy = dst_col * bw, dst_row * bh
        if sx == dx and sy == dy:
            continue
        result.paste(img.crop((sx, sy, sx + bw, sy + bh)), (dx, dy))

    result.save(path, format=(img.format or "JPEG"))


class GigaviewerUnscramblePP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)
        if not _HAS_PIL:
            self.log.warning(
                "Pillow is not installed — cannot unscramble GigaViewer images. "
                "Install it with: pip install Pillow"
            )
        job.register_hooks({"file": self.run}, options)

    def run(self, pathfmt):
        if not pathfmt.kwdict.get("_scrambled"):
            return
        if not _HAS_PIL:
            return
        path = pathfmt.temppath
        self.log.debug("gigaviewer_unscramble: unscrambling '%s'", path)
        try:
            _unscramble(path)
        except Exception as exc:
            self.log.warning("Failed to unscramble '%s': %s", path, exc)


__postprocessor__ = GigaviewerUnscramblePP
