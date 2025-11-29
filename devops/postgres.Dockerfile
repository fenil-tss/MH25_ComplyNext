FROM postgres:16

# Install pgvector from PGDG apt repo
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

# Switch back to postgres user
USER postgres

RUN mkdir -p /docker-entrypoint-initdb.d
COPY init-pgvector.sql /docker-entrypoint-initdb.d/
