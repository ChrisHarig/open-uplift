FROM node:20-slim AS dashboard-build

WORKDIR /app/dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# Install server package
COPY server/ ./server/
RUN pip install --no-cache-dir ./server

# Copy built dashboard
COPY --from=dashboard-build /app/dashboard/dist ./dashboard/dist

# Entrypoint seeds demo data on first run
COPY scripts/docker-entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Data volume
VOLUME /data
ENV OPEN_UPLIFT_DATA_DIR=/data
ENV OPEN_UPLIFT_DASHBOARD_DIR=/app/dashboard/dist

EXPOSE 7070

ENTRYPOINT ["./entrypoint.sh"]
