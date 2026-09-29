FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8000

# Override at runtime with -e LAYA_ROUTER_* (see README) as needed.
ENV LAYA_ROUTER_UPSTREAM_BASE_URL=https://api.openai.com/v1

CMD ["uvicorn", "laya_router.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
