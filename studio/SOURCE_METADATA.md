# Source metadata and counterpart connections

Historical generation15 behavior below. Registration-triggered three-site jobs,
distinct ExHentai identities, authenticated internal document requests and durable
paged searching are documented in [AUTOMATIC_SOURCES.md](AUTOMATIC_SOURCES.md).

This continuation adds a standard-library metadata reader, authenticated HTML
preview/import, direct E-Hentai/Hitomi metadata requests and bounded counterpart
discovery. Real website access, download success and NAS deployment remain
unverified. The managed cloud returned proxy CONNECT403 for `hitomi.la` and
`ltn.gold-usergeneratedcontent.net`; this is not a response from either website
and does not diagnose NAS access. No proxy, authentication or site restriction is
bypassed.

## Readers and preservation

- E-Hentai HTML: gallery ID/token declarations must match the supplied full URL.
  Title variants, namespaced tags, page count and up to100comments present in the
  current document are read. Comments are scoped by source and stable comment ID;
  absent comments do not erase previously saved entries. Additional comment or
  image pages are not fetched by HTML import.
- Hitomi HTML: the main gallery reader link must match the supplied URL. Only
  the main title/artist/language/series/character/tag areas are read; related-book
  tags are excluded. An HTML title does not become an image download request.
- Hitomi direct metadata: the fixed galleryinfo JSON assignment is decoded as
  JSON, never evaluated as JavaScript. IDs must match; artists, languages, tags
  and available file count are read. Image bytes are not requested.
- Parsed source snapshots are stored in an additive `sources.metadata` JSON
  column. Raw HTML, account details, advertising scripts and image URLs are not
  retained. The existing title and user tags are not overwritten. An empty,
  unlocked artist may be filled. Source conflicts fail instead of merging works.
- The user's supplied HTML was inspected locally only. Repository fixtures use
  invented titles, identities, tags, comments and links.

The HTML parser accepts at most2MiB,20000nodes and128levels. Source snapshots
are bounded at256KiB; authenticated JSON requests at4MiB. Imported text is escaped
in the UI. Browser-side preview is invalidated when its input changes, including
while the preview request is pending. HTML import has no external network calls.

## Shared tags and UI

`series:` maps to `parody:` and general `tag:` maps to `other:` for common
filtering; language values are case-normalized. Raw source spellings remain in
the snapshot's `raw_tags`. No speculative translation or content-tag synonym is
introduced. Common exact filters and namespace search apply these aliases, and
counts count each work once. Main search offers up to20stored tag suggestions.

`date_added:`, `timestamp:` and `source:` remain in storage/export but are hidden
from combined tag lists and suggestions. The folder-copy dialog and its polling
are removed from the normal UI; old worker/API/DB compatibility is retained.
No folder jobs, NAS files, mounts or retired copies are removed by this change.

## Counterpart discovery

The source row's counterpart action compares the other site's independent
identities. It never searches that site's equal number as an identity match.

- Hitomi to E-Hentai: ordinary public title search, at most5distinct gallery
  URLs, then each candidate's normal HTML detail document.
- E-Hentai to Hitomi: the first named artist's ordinary public `.nozomi` index,
  latest8distinct gallery IDs, then galleryinfo documents. This is deliberately
  incomplete; older works or other artist spellings can be missed. It is not a
  full Hitomi search implementation.
- At most one lookup runs per instance, with a persistent60second per-work
  attempt interval. Requests are sequential and bounded. Access/redirect/rate
  limit responses stop candidate requests. Partial/error results cannot auto-link.
- Automatic source attachment requires a single eligible candidate: normalized
  title equality, a shared artist, shared language, equal known page count and
  tag Jaccard similarity at least0.7. Missing evidence is not equality. Published
  dates and equal source numbers do not qualify a candidate.
- Ambiguous candidates are displayed with comparison evidence for manual
  selection. Already-owned identities remain attached to their original work.
  Source attachment never merges files, deletes copies or groups editions.

These rules are conservative metadata heuristics, not proof of identical page
content. Bounded searches are not exhaustive. Different translations, revised
editions and voice versions should remain separate editions. Further work is
needed for full title-index searching, background library-wide matching,
user-managed translated tag aliases and actual site-specific download validation.
The current existing download engine is unchanged and remains live-site
unverified. Standalone voice Studio development is separate.

## Validation and deployment

Run `python -m unittest discover -s studio/tests -q` and
`python -B studio/tests/metadata_smoke.py` (local Chromium/Playwright required).
The latter starts a temporary authenticated Studio and uses generated documents
and mocked counterpart responses; no private library or real website is used.
SQLite backup/reopen preserves source snapshots and original metadata.

Observed in this cloud continuation:316unit/HTTP/regression tests passed, as did
the generated Chromium desktop/mobile integration (zero page errors), JS syntax
and runtime hash checks. A fresh20000work/20000source/40000user-tag synthetic
benchmark measured median5.62ms for120item lists,103.41ms for common exact-tag
filtering,125.48ms for source-tag search and114.09ms for tag suggestions. These
are cloud measurements, not DS718+ or private-library performance guarantees.

Deployment uses the existing app-only source channel and additive DB migration.
It needs no login/worker recipe change, container privilege change, new port,
volume, credential or scheduler change. The controller backs up SQLite before
recreating Studio. Old app code ignores the extra source column, permitting code
rollback while retaining the DB. Publication is not evidence of NAS success.

Architecture was checked against EhViewer commit
[`dfe35624`](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/tree/dfe356244d234c91f2bf65af60903f80b407a838),
particularly its separate detail/page parsers, cookie store and download state.
No Java/Kotlin implementation was copied or executed. The prior supplied Hitomi
Downloader source bundle contains72other extractors, but lacks the Hitomi/E-Hentai
extractors and common downloader runtime; it was not executed or embedded.
