FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 analytics && useradd --uid 10001 --gid analytics --create-home analytics
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[cloud]'
USER 10001:10001
CMD ["insurance-analytics", "api", "--host", "0.0.0.0"]
