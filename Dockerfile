FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# This network blocks plain HTTP (port 80) but allows HTTPS - switch
# apt sources to https:// before installing anything.
RUN sed -i 's|http://archive.ubuntu.com|https://archive.ubuntu.com|g; s|http://security.ubuntu.com|https://security.ubuntu.com|g' /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || \
    sed -i 's|http://archive.ubuntu.com|https://archive.ubuntu.com|g; s|http://security.ubuntu.com|https://security.ubuntu.com|g' /etc/apt/sources.list

# Chicken-and-egg: HTTPS needs ca-certificates to verify anything, but
# ca-certificates itself must be fetched over HTTPS. Temporarily skip
# cert verification for this one install, then verification works
# normally for everything after.
RUN apt-get update \
      -o Acquire::https::Verify-Peer=false \
      -o Acquire::https::Verify-Host=false && \
    apt-get install -y --no-install-recommends ca-certificates \
      -o Acquire::https::Verify-Peer=false \
      -o Acquire::https::Verify-Host=false && \
    rm -rf /var/lib/apt/lists/*

# Ubuntu 24.04 ships Python 3.12 by default - satisfies IGRA's
# requires-python >=3.12 (pyproject.toml) without a PPA.
# PostgreSQL client tools (pg_dump, pg_restore) are a hard requirement -
# IGRA shells out to them, per ARCHITECTURE.md section 6.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        postgresql-client && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/igra-venv
ENV PATH="/opt/igra-venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Snapshots persist in .igra/ - mount this as a volume so data survives
# container restarts. See README.md for usage.
WORKDIR /workspace

ENTRYPOINT ["igra"]
CMD ["--help"]