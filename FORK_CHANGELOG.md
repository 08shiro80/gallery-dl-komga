# Fork Changelog

Changes specific to gallery-dl-komga (this fork). For upstream gallery-dl changes, see [CHANGELOG.md](CHANGELOG.md).

This fork pins the upstream version string (`1.32.1`) and tracks itself by date and commit topic. Newest first.

---

## Unreleased (in development on `master`)

### `fix(extractor/common): route any Cloudflare 403/503 through FlareSolverr`

`detect_challenge()` only flags a Cloudflare block when the body carries `_cf_chl_opt`/`jschl-answer` or the `cf-mitigated: challenge` header. Some sites (e.g. utoon.net) bot-block gallery-dl's direct request with a bare **403** that has none of those markers — FlareSolverr fetches the same URL fine (200, "challenge not detected"). The FlareSolverr fallback therefore never fired and the download failed with `403 Forbidden`. When FlareSolverr is configured (`use_fs`), `Extractor.request()` now routes **any** Cloudflare-served 403/503 (`server: cloudflare`) through FlareSolverr regardless of the body markers.

### `feat(extractor): add utoon.net and klz9.com`

- **utoon** (`utoon.net`) — Madara theme; inherits `MangaclashExtractor`, only overrides `category`/`root`.
- **klz9** (`klz9.com`) — React SPA over a signed JSON API; each request needs `x-client-ts` + `x-client-sig = sha256("<ts>.<secret>")`. Pure-API (no SPA HTML fetch), no FlareSolverr required. `status` is not emitted (the API's `m_status` is not a reliable completion flag).

### `feat(extractor,postprocessor): port copymanga, dm5, komiic, tonarinoyj + gigaviewer_unscramble from sfai05 fork`

Ported **copymanga**, **dm5**, **komiic**, **tonarinoyj** from sfai05's fork. They depend only on the stock `common` base and were registered in the static module list. komiic needs FlareSolverr (Cloudflare). tonarinoyj tags GigaViewer-scrambled pages with `#scramble`; the **`gigaviewer_unscramble`** postprocessor was ported too — it reverses the 4×4 block transposition (via Pillow) on pages flagged `_scrambled`. It self-guards on that flag, so it is a no-op for every other extractor. Activated Komga-side in `GalleryDlProcess.kt`.

### `fix(extractor/madara): status by heading label, strip description tag remnant`

`status` is now resolved by its `summary-heading` label instead of the first `summary-content` (a rating/views widget on the utoon and manhwatop skins), with fallback to the old behaviour. `description` no longer keeps the `">` opening-tag remnant. Affects the whole Madara family.

### `fix(extractor/rawkuma): chapter_minor key typo (was chapter-minor)`

The `RawkumaMangaExtractor` queued chapters with the key `chapter-minor` (hyphen) instead of `chapter_minor` (underscore). The chapter archive skip-key (`job.py`) is built from that queue kwdict, so for decimal chapters the skip-key lost its minor part and never matched the write-key — decimal chapters were re-downloaded on every resume. (Picked from the sfai05 fork; its image-extraction change in the same file was *not* taken — it targets an older rawkuma layout and would break the current CDN.)

### `fix(postprocessor/zip): close verify handle before os.replace (Windows lock)`

`ZipPP._finalize` verified the temporary archive inside a `with zipfile.ZipFile(...)` block and then called `os.replace(tmp, final)` while that handle was **still open**. On Windows (and CIFS/SMB mounts) renaming a file the same process keeps open raises `WinError 32` / "used by another process", leaving the `.cbz.part` unrenamed. The `has_entries` flag is now captured inside the `with`, the handle is closed, and only then does the rename run.

#### Modified / new files
| File | Change |
|------|--------|
| `gallery_dl/postprocessor/zip.py` | Close the verify `ZipFile` handle before `os.replace` (Windows `WinError 32` on rename of a still-open file). |
| `gallery_dl/extractor/utoon.py`, `klz9.py` | New extractors. |
| `gallery_dl/extractor/copymanga.py`, `dm5.py`, `komiic.py`, `tonarinoyj.py` | Ported from the sfai05 fork. |
| `gallery_dl/extractor/madara.py` | New `_labeled_content` helper; status-by-label (fallback preserved) + description fix. |
| `gallery_dl/extractor/rawkuma.py` | `chapter-minor` → `chapter_minor` key typo fix. |
| `gallery_dl/postprocessor/gigaviewer_unscramble.py` | Ported from the sfai05 fork; unscrambles GigaViewer `_scrambled` pages via Pillow. |
| `gallery_dl/extractor/__init__.py`, `gallery_dl/postprocessor/__init__.py` | Register the new/ported extractor and postprocessor modules. |

### Chapter-level resume system — replaces per-page archive inference

Previously the wrapper (Komga side) tried to detect which chapters were complete by reading `<Number>` from ComicInfo in existing CBZ files. That inference was per-`<Number>` and source-blind: two CBZs with the same chapter number from different sources (e.g. mgeko and MangaDex) collided, and an "interrupted-tail" recovery path destructively deleted the highest-numbered CBZ before each run. The recovery path lost three CBZs (`c005.cbz`, `c005 [In Cnnuy We Thrust].cbz`, `v1 c005 [In Cnnuy We Thrust].cbz`) of the same chapter-5 slot when the user tested an Add-Chapter-Download in a `4c08c48b-…` folder.

The replacement is a chapter-level archive written by gallery-dl itself, derived from the extractor's own deterministic fields (no URLs, no filesystem inference):

- **`postprocessor/komga.py` — chapter archive write.** After `_inject_comic_info` succeeds, `_archive_chapter` appends one line per chapter to `<cbz_parent>/.komga-archive.txt` in the format `<category> <chapter_number>`. The chapter number is `meta["chapter"] + meta["chapter_minor"]` with separators (`,`, `-`, `_`, whitespace) normalised to `.` and collapsed/stripped. Result: deterministic per chapter, immune to URL changes (mangahere.cc → mangahere.com survives), independent of `manga_id` slug renames. Example contents after a few downloads:
  ```
  mgeko 1
  mgeko 2
  mgeko 5.1
  manhuaplus 864
  ```
  MangaDex is skipped from this archive (`if category == "mangadex": return`) — MangaDex chapter URL tracking lives in Komga's `CHAPTER_URL` table and ComicInfo `<Web>`, single source of truth there.
- **`job.py` — `handle_queue` skip-check.** Before spawning a sub-job for a chapter URL, `DownloadJob.handle_queue` calls `_komga_archive_skip(url, kwdict)` which builds the same `<category> <chapter>` key from the Queue-message kwdict and checks it against the archive (lazy-loaded as a `frozenset` per job). If the key is in the archive, `return` — no sub-job, no Chapter-extractor instantiation, no page-listing HTTP fetch. For a resume after 2000 already-archived chapters this changes the cost from ~8 hours of network round-trips to a single file read plus 2000 set lookups (sub-second). The archive directory is resolved via `extractor._parentdir or extractor.config("base-directory")` because at parent-job time `self.pathfmt` isn't initialised yet.

### Atomic CBZ build — `.cbz.part` rename only after verify

`postprocessor/zip.py` writes the archive at `<chapter_name>.cbz.part` (instead of directly at `<chapter_name>.cbz`) and renames atomically to `.cbz` only at chapter-end, after the zip is closed and verified-openable. Operational implications:

- An interrupted download leaves `.cbz.part` on disk, never a half-written `.cbz`. The Komga library scanner sees only complete CBZs.
- On resume, the same path is reopened in append mode (`"a"`). With ZipPP's `"safe"` mode (also enabled in Komga's wrapper config) the central directory is flushed after every page, so existing pages are preserved across kills mid-write and the resume picks up at the next missing page.
- A `.cbz.part` that exists but fails `ZipFile(...).namelist()` open is left on disk with a warning instead of being renamed — the next run can either continue or the user can inspect.
- The fast/`mode = "safe"` distinction matters: in fast mode the central directory is only written at `finalize` close, so SIGKILL mid-chapter leaves the file unrecoverable. Komga's wrapper config now sets `"mode": "safe"` on the ZipPP block for crash-resilience.

Verified with mgeko `to-the-protagonist-and-his-childhood-friends`: SIGKILL at 8 s mid-chapter-4 left `.cbz.part` with 6 valid pages; resume preserved those 6 and appended pages 7-11; final `c004.cbz` has all 11 pages and matches the source.

#### Modified files
| File | Change |
|------|--------|
| `gallery_dl/postprocessor/komga.py` | New `_chapter_archive_key` / `_archive_chapter` methods; `_finalize` calls them per chapter after ComicInfo injection succeeds. mangadex category is skipped. Archive file is `<dirname(cbz)>/.komga-archive.txt`. Captures `self._extractor = job.extractor` in `__init__` since `PostProcessor` base class doesn't expose extractor. |
| `gallery_dl/postprocessor/zip.py` | Writes to `self.tmp_path = final_path + ".part"`, mode `"a"`. `finalize` does `os.replace(tmp_path, final_path)` only after `ZipFile(tmp_path, "r").namelist()` is non-empty. Empty `.part` (no pages written) is removed. Verify-failure keeps the `.part` for inspection. |
| `gallery_dl/job.py` | `DownloadJob.handle_queue` calls `self._komga_archive_skip(url, kwdict)` first thing after `visited.add(url)`. New `_komga_archive_skip` method reads `<extractor._parentdir or extractor.config('base-directory')>/.komga-archive.txt` once, caches as `frozenset`, returns `True` when `<category> <key>` is found. Archive read errors bubble up (no silent except). `import os` added. |

---

## 2026-06-06

### `feat(extractor/madara): parse WordPress relative-time chapter dates`

`madara._parse_date` previously only accepted absolute date strings (`May 24, 2026`, `2026-05-24`). Most Madara-based sites (manhuaplus, mangaclash, tritinia, manhwatop, deatte5) display chapter dates as WordPress `human_time_diff()` output for recent uploads — `13 hours ago`, `1 day ago`, `2 weeks ago` — and `_parse_date` returned `None` on those, so the chapter `date` field stayed unset and the Komga postprocessor skipped the `<Year>/<Month>/<Day>` tags in the resulting ComicInfo.xml. The Komga `Recently Released Books` dashboard panel filters `metadata.releaseDate > now − 1 month`, so non-MangaDex chapters with `releaseDate == null` never showed up there even though they had just been downloaded.

`_parse_date` is extended with a relative-time block: `(\d+|an?|few) (second|minute|hour|day|week|month|year)s? ago` plus the specials `today`, `yesterday`, `just now`. Result = `datetime.now(UTC).naive - delta`. Applies to all Madara-based extractors transparently. Verified with 18 test strings including `5 months ago` (`→ 2026-01-…` not `2026-05-…`, the common "5 vs 1" off-by-one I caught after first trying a too-greedy regex).

---

## 2026-06-05

### `feat(extractor/common): FlareSolverr integration with 20min cookie cache + UA sync`

Several Cloudflare-protected manga sites (mgeko.cc, mangaclash.com, deatte5.com, tritinia.org, manhwatop.com) return the Cloudflare challenge HTML to gallery-dl's `requests` session — HTTP 403 or an empty page. The fork now supports routing GET requests through a [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) endpoint when the extractor config sets `flaresolverr` to a URL string (e.g. `"http://192.168.1.10:8191/v1"`):

- **Direct-first with cookie cache.** Cached cookies + UA for a host (TTL 20 min) → direct request with those cookies attempted. On challenge HTML in the response → fallback to FlareSolverr. UserAgent sync is critical: `cf_clearance` is bound to the UA that solved the challenge; restoring cookies without restoring the UA invalidates the clearance.
- **Cold cache.** Direct POST to the FlareSolverr endpoint with `{"cmd": "request.get", "url": …}`. On success, cookies + UA are applied to `self.session` and persisted to `<tmp>/gdl_fs_cookies/<host>.pkl`.
- **Only GET requests on HTML pages.** Image downloads bypass `Extractor.request()` and go through `self.session.request()` in `downloader/http.py`, so the FlareSolverr round-trip cost only applies to chapter-listing and chapter-page HTML fetches — not to per-image downloads.

Verified with mgeko's KoSF series page: cold call 15.7 s (FlareSolverr solves challenge), warm call 5.0 s (direct with cached cookies + UA). 3× speedup on warm calls.

### `feat(extractor/mgreadio): mgread.io extractor with paginated chapter listing`

Custom extractor for mgread.io. Chapter listing is paginated under `/manga/<slug>/chapter/page/{N}/`; images are served from `mg.mgread.io` CDN and lazy-loaded via the standard `<img class="…wp-manga-chapter-img…">` pattern. Handled in `_chapter_list` (walks pages 1..100 until first empty page) and `_chapter_images`.

### `feat(extractor/deatte5): Deatte5 extractor for single-slug chapter URLs`

deatte5.com uses a single-slug-per-chapter URL scheme: `/manga/<series>-chapter-<N>/` rather than the standard Madara `/manga/<series>/<chapter>/` split. Pattern `r"/manga/([a-z0-9-]+?)-(chapter-\d+(?:-\d+)?)/?"` with a lazy quantifier on the first group; groups[0] = manga_slug, groups[1] = chapter_slug. Skips the `_manga_info` round-trip (deatte5 has no per-series manga page) — slug-derived display name is sufficient. Custom `_chapter_images` because MangaClash's container-based slice (`text.extr` around `"reading-content"`) falsely matched a CSS `@media` rule on deatte5; this implementation greps `<img class=".*wp-manga-chapter-img.*">` from the whole page. Verified: 17 image URLs extracted from `/manga/deatte-5-byou-de-battle-chapter-170/`.

### `feat(extractor/manhwatop): ManhwaTop extractor (inherits Mangaclash)`

Trivial Madara subclass deriving from `MangaclashExtractor` (which already has the `reading-content` slice fix). One file, three lines of useful code.

### `feat(extractor/mgeko): Mgeko extractor (custom, manga-page-free items)`

mgeko.cc has URL quirks: chapter URLs use **two different manga slugs** for the same series (old `<series>-chapter-N-eng-li`, new `<series>-famil-chapter-N-eng-li`), and the manga page is only reachable under the `-famil` variant. This extractor skips the manga-page request entirely — `manga_slug` is derived from the chapter slug, the slug-derived display name is good enough. `_chapter_list` parses `/manga/<slug>/all-chapters/` (all chapters in one HTML, no pagination needed) and follows the `href` for relative `/reader/en/` URLs with absolute normalisation. `_chapter_images` filters all `<img>` tags with regex `/cdn_mangaraw/.../chapter-N/<file>.<ext>` — mgeko's filename pattern is variable (`01.jpg`, `01result.jpg`, `1.jpg`).

### `feat(extractor/tritinia): Tritinia extractor with ch-N slug pattern`

Madara subclass with `ch-N` URL slug pattern instead of `chapter-N`. `_chapter_images` override iterates `<div class="page-break">` blocks instead of taking the first matching `div`.

### `feat(extractor/mangaclash): MangaClash extractor with reading-content slice fix`

Madara subclass. `_chapter_images` override uses a refined slice: `class="reading-content"` followed by a closing quote, plus a `wp-manga-chapter-img` class filter. The upstream Madara slice matched too broadly on mangaclash's HTML structure.

### `feat(extractor): auto-discovery via _modules_internal() in __init__.py`

Adding a new extractor module to the fork previously required editing the static `modules` list in `gallery_dl/extractor/__init__.py`. The new `_modules_internal()` walks the extractor directory and yields every `.py` module name, layered on top of the static list. Effect: dropping a new extractor file in is enough — no list edit. Static `modules` keeps its existing entries for upstream-merge stability.

### `fix(postprocessor/komga): keep existing series.json, don't overwrite enriched metadata`

`_write_series_json` previously compared the existing `series.json` byte-for-byte and overwrote it whenever the content differed. Komga's Auto-Match step enriches `series.json` after the first download with MangaDex/AniList/Kitsu metadata and `tracker_links` — that enrichment always differs from the gallery-dl extractor-derived output, so every resume run silently destroyed it. Symptom: scan a series, Komga auto-matches and writes rich metadata, run a resume download for one new chapter, the rich metadata is back to the minimal extractor-derived version.

Fix: write `series.json` **only when the file doesn't already exist**. Komga owns enrichment from that point on; the fork seeds it once for fresh series.

---

## 2026-05-29

### `fix(madara): correct image download, ComicInfo metadata, chapter date + <Web>`

`_manga_info` `<h1>` filter (previously the whole `title_block` including the sibling HOT-badge was stripped → "Hot Magic Emperor" leaked as plain text instead of "Magic Emperor"). Triggered an 864-chapter re-download disaster on manhuaplus when Komga's resume path mismatched titles. `_chapter_list` changed from 2-tuples to 3-tuples (added chapter date). ComicInfo `<Web>` field now correctly carries the source URL.

---

## 2026-05-27

### `feat(extractors,postprocessor): merge genres into tags`

Genres and tags were being written as separate fields in metadata but consumed identically by downstream tooling (Komga reads both as series tags). Merged in the metadata pipeline so a single concatenated set ends up in ComicInfo.xml `<Genre>` and `series.json` `genres`.

---

## Workflow + CI (pre-fork-features)

The earliest fork commits (`3f8cf54f1`, `459f7f3c2`, `77c6a70f9` from May 2026) tighten the upstream release workflow: pin GitHub Actions to commit hashes, improve release-body formatting, extract `git clone` into a custom action. These don't affect runtime behaviour; they're build-pipeline hygiene to keep the fork's docker-image releases reproducible.

---

## Fork base

The fork branched from upstream gallery-dl `1.32.1` (`fdcaab3c4`). Subsequent upstream merges, when they happen, are documented in the section header as "Upstream merge: X.Y.Z" with a per-file note for any conflict resolution decisions. The fork keeps the version string at `1.32.1` so end-users installing via `pip install gallery-dl-komga` see a stable identifier independent of the fork's continuous change rate.
