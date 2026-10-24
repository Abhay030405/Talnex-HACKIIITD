FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -o /out/ ./cmd/api ./cmd/worker ./cmd/migrate

FROM alpine:3.21
RUN apk add --no-cache ca-certificates wget \
 && adduser -D -u 10001 talnex
COPY --from=build /out/api /out/worker /out/migrate /usr/local/bin/
COPY migrations /app/migrations
USER talnex
EXPOSE 8080
CMD ["api"]
