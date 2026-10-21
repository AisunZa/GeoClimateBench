FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN python -m pip install --no-cache-dir \
    numpy==1.26.4 pandas==2.2.3 scipy==1.14.1 xarray==2024.10.0

# The verifier is built independently. It receives only the declared agent
# artifacts, not the agent container filesystem.
COPY . /tests/
RUN mkdir -p /app/results /app/data /logs/verifier
CMD ["/bin/bash"]
