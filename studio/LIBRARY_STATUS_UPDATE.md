# Library status update

Directly connected CBZ files need no image-folder copy job. The optional copy dialog now says when to use it, and the library no longer treats historical copy receipts as the catalog total.

The authenticated status API reports indexed catalog files, metadata-only entries, pending uploads and distinct works linked to known upload records. Multiple upload records for one work count once. Counts do not establish physical storage location, duplicate identity or current file readability. No file deletion, conversion, mount change or worker privilege change is included.

The separately installed folder worker remains pinned to its previously reviewed runtime. Its installer regression now checks an archived manifest rather than requiring the current app manifest to stay unchanged.

Validation:194unit/HTTP/deployment tests passed; JavaScript syntax and diff checks passed. `python -B studio/tests/library_status_smoke.py` passed with generated records in Chromium at desktop/mobile sizes, including empty library, indexed files, metadata-only entries, repeated upload links and API failure. No personal media or NAS management access was used. Publishing a release request does not confirm installation on a device.
