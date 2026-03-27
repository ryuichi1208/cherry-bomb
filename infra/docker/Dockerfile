FROM python:3.14-slim AS base

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ src/

# Install dependencies
RUN uv sync --frozen --no-dev

# Runtime
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "cherry_bomb.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
