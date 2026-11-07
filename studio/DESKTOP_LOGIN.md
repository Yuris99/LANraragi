# Ordinary NAS browser login

Production login uses an ordinary visible Chromium process in a private Xvfb
display. Studio relays screenshots and explicit user mouse/keyboard/scroll input
through X11. No CDP, WebDriver, headless, stealth or challenge-solving connection
is attached. Playwright is used only for explicit generated-route fixtures and
the test's separate Studio client browser.

Click the preview to type or paste directly; a native private input captures
committed IME text and mobile keyboard input. Explicit actions are serialized,
adjacent queued text is combined, and preview polling never disables capture.
Wheel and vertical touch gestures scroll remotely. Escape releases keyboard
capture to the visible keyboard button; the collapsed text tool remains a fallback.
No keyboard events are captured outside this focused input.

E-Hentai and ExHentai share one account vault and one login control. A new private
browser restores saved account cookies with their original domains. Restoration
runs only on the extension's initial install, so idle wake cannot overwrite a
later login. Fixed buttons open either host. EH-only cookies never become EX
cookies, and a saved session with no matching domain fails before any request.

Legacy account files are read without migration writes. Explicit Save writes the
shared Netscape file at ehentai.cookies with a format marker; an older EX file
remains a private backup and is no longer read. Conflicting account identities
require explicit resaving. Shared Forget removes both legacy account files.
Existing E/X links and source URL fields remain compatible. Grouped display
preserves files, work records and editions, and does not merge their storage.

The existing nonroot UID, read-only root, 1GiB memory, private tmpfs, dropped
capabilities and no-host-port configuration remain. There is no VNC/debug port,
Docker socket or original-library mount. X11 uses a private Xauthority cookie
and does not listen on TCP. Chromium still uses the documented --no-sandbox
container setting; this does not assert DSM browser process-sandbox support.
Fixed Chromium URL policies limit navigation to the supported site families and
the exact official verification host. Downloads, password saving and sync are
disabled. Managed-cloud proxy/CA policy is preserved, not bypassed.

## Explicit account save

A private ephemeral extension has only the cookies permission and fixed host
permissions. It changes no website scripts, browser APIs or fingerprint signals.
Cookie read permissions cover both HTTP and HTTPS for the selected provider:
Chromium filters Secure=false cookies against HTTP host permissions, including
cookies originally set during HTTPS login. Navigation remains HTTPS-only under
the unchanged browser policy. This grants no unrelated host or arbitrary URL.
Studio's Save button opens a 15-second server-side save window and sends the
extension's keyboard command. Only then are selected-provider account cookies
sent to a token-protected NAS-loopback endpoint. A current window nonce and
recent Save are required. No profile decryption or PC-profile access occurs.
Passwords and cookies never enter command arguments, logs or cloud requests.

Cloudflare clearance/challenge names (cf_* and __cf*) are excluded on export
and on vault read/write. Older vault files cannot forward them to engines.
A blocked download endpoint stays blocked: real site login/download support
remains unverified until tested normally. ExHentai downloading remains disabled.

Only confirmed account save closes the preview and refreshes saved status.
An extension response timeout or rejected empty cookie export remains visible
across preview refreshes and preserves an older saved session. Retrying Save
clears the previous failure. Callback failures never imply successful storage.
Profile, display key, screenshots and extension token use private temporary files
and are destroyed on cancel/save or after thirty minutes without user input.
Valid clicks, text, keys, scrolls, site visits and Save renew this idle deadline;
automatic screenshot/status polling and cookie export callbacks do not. Screenshots are
unlinked immediately after capture. Container interruption loses its tmpfs.
The account vault retains existing 0700/0600 and atomic-save rules.

## One local recipe upgrade

The installed root controller freezes Dockerfiles, so app source updates cannot
add X11 packages. `upgrade-desktop-login.sh` requires the existing dedicated root,
reviewed source commit and manifest SHA. A pinned launcher is supplied with the
release and preserves the existing scheduler and enabled/disabled preference.

Upgrade verifies existing files/configs, acquires both update locks, checks eight
allowlisted files and requires byte-identical Compose files. Prior frozen files
are retained in before-desktop-login. Observed copy/validation failure restores
them. Power interruption or a retained backup requires local review; never force
a lock or overwrite the backup. New controllers read nas-desktop-services.json;
older controllers keep nas-services.json and are not silently migrated.

The same login/worker project, UID, mounts and key/session volumes remain.
No NAS media, DB, account, ACL, firewall, LANraragi, Stash/NMLO or scheduler
change is included. Successful recipe installation is distinct from image build,
browser launch, actual website authentication and actual download success.

The pinned launcher and installer retry transient DNS/connect/timeout/transfer
errors on the same HTTPS URL, at most four attempts with bounded delays. HTTP
denials and certificate errors stop immediately. Exhausted pre-install transfers
remove only their own stage/locks and preserve all existing frozen files.

## Validation boundary

Generated tests cover real nonroot/read-only Docker, Xvfb, ordinary Chromium,
remote input, explicit account export, challenge-cookie exclusion and temporary
profile cleanup. Separate Studio UI coverage verifies asynchronous save and status
refresh. No real account, site security challenge or NAS deployment is used.
Actual DS718+ login and downloader behavior require operator verification.

2026-10-22 validation: 304 unit/regression tests passed. The production-style
nonroot/read-only, 1GiB, PID-128 generated desktop run passed real Xvfb/Chromium
input, account export and profile removal. The additional Studio UI harness used
PID-256 only to host its extra automated client browser; it confirmed async Save,
closed preview and refreshed saved status, with no secret values in the DOM or
localStorage. Neither run used a real website, account, media or NAS.

References: [Cloudflare supported browsers](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/)
and [Chromium URL policy format](https://support.google.com/chrome/a/answer/9942583?hl=en).
