FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
WORKDIR /workspace
COPY pyproject.toml README.md LICENSE ./
COPY geoclimatebench/ ./geoclimatebench/
RUN pip install --no-cache-dir -e '.[dev]'
COPY tests/ ./tests/
CMD ["sh", "-c", "python -m pytest -q && python -m geoclimatebench demo --data-dir /workspace/data --output /workspace/results"]
