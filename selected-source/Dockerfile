# FaultSage Cloud image (D-018): FastAPI serving the API and the built React app.
# Stage 1 builds the web app; stage 2 installs the Python package with the cloud extra.

FROM node:22.11-bookworm-slim AS web
WORKDIR /src
COPY design/ design/
COPY web/package.json web/package-lock.json web/.npmrc web/
RUN cd web && npm ci --no-fund --no-audit
COPY web/ web/
RUN cd web && npx vite build --outDir /out

# pg_dump, pg_restore and psql for backups and restores. Debian bookworm ships pg_dump 15, which refuses to dump a
# newer server; take pg_dump 17 (dumps servers up to 17) from the official image, same Debian base.
FROM postgres:17.2-bookworm AS pgclient
RUN mkdir -p /out/lib && cp /usr/lib/postgresql/17/bin/pg_dump /usr/lib/postgresql/17/bin/pg_restore \
       /usr/lib/postgresql/17/bin/psql /out/ \
    && cp -L "$(ldconfig -p | awk '/libpq\.so\.5 /{print $NF; exit}')" /out/lib/libpq.so.5

FROM python:3.12.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FAULTSAGE_ENV=production FAULTSAGE_TRUSTED_PROXY=true PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends libldap-2.5-0 libgssapi-krb5-2 libreadline8 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 faultsage
COPY --from=pgclient /out/pg_dump /out/pg_restore /out/psql /usr/local/bin/
COPY --from=pgclient /out/lib/libpq.so.5 /usr/local/lib/libpq.so.5
RUN ldconfig && pg_dump --version && pg_restore --version && psql --version
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
COPY engine/ engine/
COPY --from=web /out src/faultsage/static/app
RUN pip install ".[cloud]" ./engine
# The CLI installer customers download from this site (/download/<wheel>): the public package with
# the built dashboard, without the ranking engine.
RUN pip wheel --no-deps --wheel-dir /app/downloads . && ls /app/downloads
USER faultsage
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz',timeout=4)"
# Inside a container the server must listen on all interfaces; the platform's proxy is the edge.
ENV FAULTSAGE_BIND=0.0.0.0
CMD ["faultsage-cloud", "serve"]
