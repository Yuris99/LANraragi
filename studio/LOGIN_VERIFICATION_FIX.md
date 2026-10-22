# Login verification dependency and visible startup state

The reported login screenshot identified a security verification failure that
explicitly required challenges.cloudflare.com. The browser's original site-only
request filter blocked this legitimate dependency. Allow its exact hostname over
HTTPS port 443 for resources and child-frame navigation while an approved site
is the top-level page. Keep other hosts, alternate ports and top-level navigation
outside the selected site blocked. Do not add stealth, challenge solving, network
switching or authentication bypass. Saved sessions remain scoped to their provider.

Show elapsed startup time, a request deadline and persistent inline errors rather
than a silently disabled button. Distinguish browser startup, site timeout, site
connectivity and preview failures through fixed error codes; never forward raw
upstream bodies. Distinguish blocked subresources from blocked main-frame navigation
and show main-document HTTP errors. A 200 response does not prove authentication.

Regression coverage uses generated routes, including slow page delivery, official
verification-host resources, a blocked unrelated resource, synthetic HTTP 403,
explicit login/save and error-body redaction. No real challenge is solved and no
real account is used. NAS service connectivity previously reported healthy does
not establish actual login or website download support. The corrected dependency
still requires a real NAS/user verification after the scheduled service update.
