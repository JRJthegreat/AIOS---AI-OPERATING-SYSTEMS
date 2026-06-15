# Microsoft Playwright Python image — includes Chromium + all browser deps.
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /usr/src/app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure Chromium is installed for Playwright
RUN playwright install chromium

# Copy actor metadata and source
COPY .actor/ ./.actor/
COPY src/ ./src/

# Apify actors run as non-root
RUN chown -R myuser:myuser /usr/src/app 2>/dev/null || true

CMD ["python", "-m", "src"]
