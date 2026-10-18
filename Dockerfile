# infogen: Ubuntu desktop (XFCE over noVNC) + Firefox + Claude Code + the infographic toolkit, Remotion templates and API.
# Same operating model as the docgen (documentary) image. Builds for arm64 (CodeBuild, Graviton) and amd64 (local testing).
# No secrets and no Claude config in the image.
FROM ubuntu:24.04
ARG TARGETARCH
ARG GIT_SHA=dev
# Pinned like docgen: bump deliberately; the smoke test in buildspec.yml gates the push.
ARG CLAUDE_CODE_VERSION=2.1.296
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

# upgrade first: the base image lags behind Ubuntu's security updates
# fonts-montserrat: the captions font (libass); the templates bundle their own copy of Montserrat
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
      xfce4 xfce4-terminal dbus-x11 tigervnc-standalone-server tigervnc-tools novnc websockify \
      ffmpeg python3 python3-pip python3-pil python3-numpy git curl ca-certificates gnupg supervisor sudo \
      fonts-dejavu-core fonts-noto-color-emoji fonts-montserrat xdg-utils nano less jq unzip procps \
      libnss3 libdbus-1-3 libatk1.0-0t64 libatk-bridge2.0-0t64 libgbm1 libasound2t64 libxrandr2 libxkbcommon0 \
      libxfixes3 libxcomposite1 libxdamage1 libpango-1.0-0 libcairo2 libcups2t64 \
 && rm -rf /var/lib/apt/lists/* && fc-cache -f

# Firefox from Mozilla's apt repository (Ubuntu's own package is a snap, which does not run in a container)
RUN install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg -o /etc/apt/keyrings/packages.mozilla.org.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list \
 && printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla \
 && apt-get update && apt-get install -y --no-install-recommends firefox && rm -rf /var/lib/apt/lists/*

# Node 24 and Claude Code
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/* \
 && npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} && npm cache clean --force

# VS Code for maintaining the scripts and templates from the desktop
RUN A=$([ "$TARGETARCH" = "arm64" ] && echo arm64 || echo x64) \
 && curl -fsSL "https://update.code.visualstudio.com/latest/linux-deb-$A/stable" -o /tmp/code.deb \
 && apt-get update && (echo "code code/add-microsoft-repo boolean false" | debconf-set-selections) \
 && apt-get install -y --no-install-recommends /tmp/code.deb && rm -rf /tmp/code.deb /var/lib/apt/lists/*

# --ignore-installed: Debian ships typing_extensions without pip metadata, so pip cannot upgrade it in place
RUN pip3 install --no-cache-dir --break-system-packages --ignore-installed fastapi uvicorn pydantic boto3

# ubuntu:24.04 ships a user with uid 1000; replace it so files on the volumes are owned by infogen
RUN userdel -r ubuntu 2>/dev/null || true; useradd -m -u 1000 -s /bin/bash infogen \
 && mkdir -p /data/runs /data/claude && chown -R infogen:infogen /data

COPY --chown=infogen:infogen remotion/package.json remotion/package-lock.json /app/remotion/
USER infogen
# Remotion's packages and its headless browser first, so template edits do not reinstall them
RUN cd /app/remotion && npm ci --no-audit --no-fund && npx remotion browser ensure && npm cache clean --force
USER root
COPY --chown=infogen:infogen infogen/ /app/infogen/
COPY --chown=infogen:infogen api/ /app/api/
COPY --chown=infogen:infogen prompts/ /app/prompts/
COPY --chown=infogen:infogen docs/ /app/docs/
COPY --chown=infogen:infogen remotion/ /app/remotion/
COPY deploy/supervisord.conf /etc/infogen/supervisord.conf
COPY deploy/entrypoint.sh /usr/local/bin/infogen-entrypoint
COPY deploy/start-desktop.sh /usr/local/bin/infogen-start-desktop
RUN chmod +x /usr/local/bin/infogen-entrypoint /usr/local/bin/infogen-start-desktop

USER infogen
# Bundle the templates now so a render does not have to, and synthesise the sound effects once.
RUN cd /app/remotion && npx remotion bundle src/index.ts --out-dir bundle --log=error \
 && cd /app && PYTHONPATH=/app python3 -m infogen sfx --out /app/sfx
WORKDIR /data/runs
ENV HOME=/home/infogen DISPLAY=:1 BROWSER=firefox PYTHONPATH=/app PYTHONUNBUFFERED=1 INFOGEN_APP=/app INFOGEN_SFX_DIR=/app/sfx \
    CLAUDE_CONFIG_DIR=/data/claude INFOGEN_GEOMETRY=1600x900 INFOGEN_RUNS_DIR=/data/runs INFOGEN_IMAGE=infogen:${GIT_SHA}
EXPOSE 6080 8080
ENTRYPOINT ["infogen-entrypoint"]
