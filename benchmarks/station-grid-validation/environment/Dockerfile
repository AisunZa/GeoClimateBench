FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Installed only at image-build time; task execution has no network access.
RUN python -m pip install --no-cache-dir \
    numpy==1.26.4 pandas==2.2.3 scipy==1.14.1 xarray==2024.10.0

COPY data/daily_max.nc /app/data/daily_max.nc
COPY data/stations_synthetic.csv /app/data/stations_synthetic.csv
RUN mkdir -p /app/results
CMD ["/bin/bash"]
