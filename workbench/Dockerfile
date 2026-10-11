# NOT YET BUILT: written in a sandbox without Docker (ADR-12). Development image only, for synthetic data.
# Build from the research pack root so the image contains the schemas, config and API contract it reads:
#   docker build -f workbench/Dockerfile -t aw-workbench .
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AW_PACK_DIR=/pack AW_OBJECT_STORE_DIR=/data/objects
RUN useradd --create-home --uid 10001 aw && mkdir -p /data/objects && chown aw /data/objects
WORKDIR /pack
COPY schemas ./schemas
COPY config ./config
COPY api ./api
COPY db ./db
COPY fixtures ./fixtures
COPY workbench ./workbench
# psycopg is left out on purpose: its code path is untested (ADR-12.2), so the image uses the tested stdlib client.
RUN pip install --no-cache-dir -e ./workbench
USER aw
WORKDIR /pack/workbench
EXPOSE 8080
# AW_ENV=dev keeps /dev/login available. AW_BIND_ANY lets the dev server listen on the container interface;
# docker-compose.yml publishes it on the host's loopback interface only. Never expose this image publicly.
ENV AW_BIND_ANY=1
CMD ["python", "-m", "aw.server", "--host", "0.0.0.0", "--port", "8080"]
