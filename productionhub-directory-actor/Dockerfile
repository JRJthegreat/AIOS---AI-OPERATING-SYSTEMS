# Microsoft Playwright Python image — includes Chromium + all browser deps.
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /usr/src/app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Patchright's patched Chromium, plus real Google Chrome — Cloudflare clears
# with channel="chrome" (verified locally) but loops forever on bare Chromium
# in the cloud ("Verification successful. Waiting for … to respond").
# _launch_context prefers the chrome channel when present.
RUN patchright install chromium && patchright install chrome

# Copy actor metadata and source
COPY .actor/ ./.actor/
COPY src/ ./src/

# Apify actors run as non-root
RUN chown -R myuser:myuser /usr/src/app 2>/dev/null || true

# Cloudflare's JS challenge fails in headless mode, so the scraper runs a
# headed (patchright) Chromium inside a virtual display.
CMD ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1280x960x24", "python", "-m", "src"]
