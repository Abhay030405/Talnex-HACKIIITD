FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Only the standalone server and static files go into the final image, run as a plain user.
FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN adduser -D -u 10001 talnex
COPY --from=build --chown=talnex /app/.next/standalone ./
COPY --from=build --chown=talnex /app/.next/static ./.next/static
USER talnex
EXPOSE 3000
CMD ["node", "server.js"]
