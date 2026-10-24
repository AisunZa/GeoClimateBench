FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Fixed scientific runtime. Dependencies are downloaded at IMAGE BUILD time,
# not during the agent/verification phase.
RUN python -m pip install --no-cache-dir \
    numpy==1.26.4 pandas==2.2.3 scipy==1.14.1 xarray==2024.10.0

COPY data/hourly_synthetic.nc /app/data/hourly_synthetic.nc
RUN mkdir -p /app/results
CMD ["/bin/bash"]
