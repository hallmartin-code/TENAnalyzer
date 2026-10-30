# Railway builds this image. Everything the app needs is baked in; the API key is not.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# LibreOffice: legacy .ppt conversion and .pptx slide rendering for visual inspection.
# Tesseract: OCR for scanned PDF pages. Together they add roughly 500 MB to the image;
# remove this layer for a smaller image (the app degrades gracefully and says so).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-impress fonts-dejavu-core \
      tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer first, so code edits do not reinstall everything.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY ten_screener ./ten_screener
COPY assets ./assets
COPY static ./static
COPY templates ./templates
COPY .streamlit ./.streamlit
COPY app.py README.md ./

# Uploads are processed in per-request temp directories and deleted; nothing is written elsewhere.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501
ENV PORT=8501

# Railway injects $PORT. Streamlit must bind 0.0.0.0 to be reachable, headless mode stops it
# opening a browser, and the file watcher is off because the image is immutable.
CMD ["sh", "-c", "python -m streamlit run app.py \
  --server.port=${PORT:-8501} \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --server.fileWatcherType=none \
  --server.maxUploadSize=${TEN_MAX_UPLOAD_MB:-50} \
  --browser.gatherUsageStats=false"]
