# -*- coding: utf-8 -*-

# Copyright 2018-2022 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Store files in ZIP archives"""

from .common import PostProcessor
from .. import util
import zipfile
import os


class ZipPP(PostProcessor):

    COMPRESSION_ALGORITHMS = {
        "store": zipfile.ZIP_STORED,
        "zip"  : zipfile.ZIP_DEFLATED,
        "bzip2": zipfile.ZIP_BZIP2,
        "lzma" : zipfile.ZIP_LZMA,
    }

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)
        self.delete = not options.get("keep-files", False)
        self.files = options.get("files")
        ext = "." + options.get("extension", "zip")
        algorithm = options.get("compression", "store")
        if algorithm not in self.COMPRESSION_ALGORITHMS:
            self.log.warning(
                "unknown compression algorithm '%s'; falling back to 'store'",
                algorithm)
            algorithm = "store"

        self.zfile = None
        self.path = job.pathfmt.realdirectory[:-1]
        self.final_path = self.path + ext
        self.tmp_path = self.final_path + ".part"
        self.args = (self.tmp_path, "a",
                     self.COMPRESSION_ALGORITHMS[algorithm], True)

        job.register_hooks({
            "file": (self.write_safe if options.get("mode") == "safe" else
                     self.write_fast),
        }, options)
        job.hooks["finalize"].append(self.finalize)

    def open(self):
        try:
            return zipfile.ZipFile(*self.args)
        except FileNotFoundError:
            os.makedirs(os.path.dirname(self.tmp_path))
            return zipfile.ZipFile(*self.args)

    def write(self, pathfmt, zfile):
        # 'NameToInfo' is not officially documented, but it's available
        # for all supported Python versions and using it directly is a lot
        # faster than calling getinfo()
        if self.files:
            self.write_extra(pathfmt, zfile, self.files)
            self.files = None
        if pathfmt.filename not in zfile.NameToInfo:
            zfile.write(pathfmt.temppath, pathfmt.filename)
            pathfmt.delete = self.delete

    def write_fast(self, pathfmt):
        if self.zfile is None:
            self.zfile = self.open()
        self.write(pathfmt, self.zfile)

    def write_safe(self, pathfmt):
        with self.open() as zfile:
            self.write(pathfmt, zfile)

    def write_extra(self, pathfmt, zfile, files):
        for path in map(util.expand_path, files):
            if not os.path.isabs(path):
                path = os.path.join(pathfmt.realdirectory, path)
            try:
                zfile.write(path, os.path.basename(path))
            except OSError as exc:
                self.log.warning(
                    "Unable to write %s to %s", path, zfile.filename)
                self.log.debug("%s: %s", exc, exc.__class__.__name__)
                pass
            else:
                if self.delete:
                    util.remove_file(path)

    def finalize(self, pathfmt):
        if self.zfile:
            self.zfile.close()

        if self.delete:
            util.remove_directory(self.path)

            if self.zfile and not self.zfile.NameToInfo:
                util.remove_file(self.tmp_path)
                return

        if os.path.isfile(self.tmp_path):
            try:
                with zipfile.ZipFile(self.tmp_path, "r") as verify:
                    has_entries = bool(verify.namelist())
                # Close the verify handle before renaming: on Windows os.replace()
                # of a still-open file raises WinError 32 ("used by another process"),
                # which left the .cbz.part unrenamed.
                if has_entries:
                    os.replace(self.tmp_path, self.final_path)
            except (zipfile.BadZipFile, OSError) as exc:
                self.log.warning(
                    "Keeping %s for resume after verify failure: %s",
                    self.tmp_path, exc)


__postprocessor__ = ZipPP
