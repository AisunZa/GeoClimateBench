FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN python -m pip install --no-cache-dir \
    numpy==1.26.4 pandas==2.2.3 scipy==1.14.1 xarray==2024.10.0

# Tests are shipped only in the independent verifier image, never the agent image.
COPY . /tests/
RUN mkdir -p /app/results /logs/verifier
CMD ["/bin/bash"]
