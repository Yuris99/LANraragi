# Library domain and Audio subpath

The existing Library URL remains `https://library.yuris.io/#/library`.
Audio uses `https://library.yuris.io/audio/`. The standalone NAS Audio address
remains available at `http://192.168.219.122:43136/`.

Audio accepts its existing root routes and the same routes under `/audio/`.
Static assets and export links are relative; the app and player prefix their
API, cover, subtitle and media requests when opened under `/audio/`.
`/audio` redirects to `/audio/`, retaining the query string.

The existing domain NGINX gateway routes `/audio/` to the existing Audio port
without stripping the prefix. Its Library route stays unchanged. Audio's
explicit Host allowlist includes both the NAS IP and `library.yuris.io`;
Basic authentication and same-origin write validation remain enabled.
The proxy forwards the public Host and the existing authorization header.

The apps still have their existing authentication realms. This routing change
does not add single sign-on or a shared in-app navigation menu. Server-side
IDs, original titles, translations and playback progress stay in the existing
Audio data volume. Browser-only favorites, personal tags and display settings
remain scoped to their original browser origin; they are not automatically
copied from the NAS IP origin to the HTTPS domain.

Deployment evidence and rollback copies are kept in the ignored
`data/domain-audio-main-20261106/` directory. NAS backups include the original
Audio Compose file and the gateway's original `nginx.conf`. Do not apply an
old configuration without first comparing the current service configuration.

Checks cover authenticated root and prefixed routes, media byte ranges,
static MIME/CSP, same-origin write protection, malformed request targets,
and synthetic player/library flows at both paths. Live browser verification
blocks all writes and playback; it does not validate extended real playback.
