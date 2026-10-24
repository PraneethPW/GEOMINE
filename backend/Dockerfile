FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libexpat1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.lock ./
RUN pip install -r requirements.lock
RUN python -c "import rasterio, scipy, shapely, pyproj; print('Geospatial runtime imports verified')"
ARG INSTALL_ML=false
COPY requirements-ml.txt ./
RUN if [ "$INSTALL_ML" = "true" ]; then pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu; fi
COPY app ./app
RUN useradd --create-home --uid 10001 geomine
USER geomine
EXPOSE 8000
CMD ["python", "-m", "app.server"]
