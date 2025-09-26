FROM docker.io/python:3.13
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync
COPY . ./
RUN uv sync
ENTRYPOINT ["uv", "run"]
