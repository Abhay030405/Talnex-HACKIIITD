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
# The standalone build leaves out public/ (the logo, the intro film and posters), so it is copied in on its own.
COPY --from=build --chown=talnex /app/public ./public
USER talnex
EXPOSE 3000
CMD ["node", "server.js"]
