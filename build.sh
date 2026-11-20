#!/usr/bin/env bash
# Build every DukeyOS service on your PC (Go 1.21+ and internet access). Output: dist/
# Then copy this whole folder to the server and run:  sudo ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
command -v go >/dev/null || { echo "Go 1.21+ is required: https://go.dev/dl/" >&2; exit 1; }
GOVER=$(go env GOVERSION | sed 's/^go//'); echo "using Go $GOVER"
mkdir -p dist
export GOOS=linux GOARCH=amd64 CGO_ENABLED=0
# The generated API/client packages (codegen/) are not committed: every //go:generate line pins its own
# oapi-codegen version (go run ...@v1.12.4), so nothing needs installing first.
for d in messagebus common core gateway usersvc appmanagement localstorage; do
  echo "generating $d"; (cd "$d" && go generate ./... )
done
for p in core:dukeyos-core gateway:dukeyos-gateway usersvc:dukeyos-usersvc appmanagement:dukeyos-appmanagement localstorage:dukeyos-localstorage messagebus:dukeyos-messagebus; do
  d=${p%%:*}; b=${p##*:}; echo "building $b"
  (cd "$d" && go mod tidy && go build -trimpath -ldflags "-s -w" -o "../dist/$b" .)
done
echo "done -> dist/   (copy this whole folder to the server, then: sudo ./install.sh)"
