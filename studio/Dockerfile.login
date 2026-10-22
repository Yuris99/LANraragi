# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN --mount=type=secret,id=proxy_ca,mode=0444 \
    studio_ca_bundle=/etc/ssl/certs/ca-certificates.crt; \
    if [ -f /run/secrets/proxy_ca ]; then studio_ca_bundle=/run/secrets/proxy_ca; fi; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources; \
    apt-get -o Acquire::https::CaInfo="$studio_ca_bundle" update && apt-get -o Acquire::https::CaInfo="$studio_ca_bundle" install -y --no-install-recommends chromium fonts-noto-cjk ca-certificates xvfb xauth xdotool scrot && \
    rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=proxy_ca,mode=0444 \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir playwright==1.62.0
RUN mkdir -p /etc/chromium/policies/managed && printf '%s\n' '{"URLBlocklist":["*"],"URLAllowlist":["https://e-hentai.org:443","https://exhentai.org:443","https://nhentai.net:443","https://.challenges.cloudflare.com:443","http://.127.0.0.1:8091/rpc","chrome-extension://*"],"DownloadRestrictions":3,"PasswordManagerEnabled":false,"BrowserSignin":0,"SyncDisabled":true}' > /etc/chromium/policies/managed/studio.json
COPY studio/login_service.py studio/site_sessions.py studio/init_login.py ./
RUN chmod -R a+rX /app && useradd --uid 9001 --create-home studio
USER studio
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp STUDIO_SESSION_DIR=/sessions STUDIO_LOGIN_TOKEN_FILE=/run/studio-login/token
CMD ["python","login_service.py"]
