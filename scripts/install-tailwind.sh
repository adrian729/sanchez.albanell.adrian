#!/usr/bin/env bash
set -euo pipefail

# Downloads the Tailwind CSS v4 standalone CLI binary for the current platform
# into bin/tailwindcss. No Node required.
#
# Usage: ./scripts/install-tailwind.sh

cd "$(dirname "$0")/.."

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Darwin)
    case "$ARCH" in
      arm64)  ASSET="tailwindcss-macos-arm64" ;;
      x86_64) ASSET="tailwindcss-macos-x64" ;;
      *) echo "Unsupported macOS arch: $ARCH" >&2; exit 1 ;;
    esac
    ;;
  Linux)
    case "$ARCH" in
      aarch64|arm64) ASSET="tailwindcss-linux-arm64" ;;
      x86_64)        ASSET="tailwindcss-linux-x64" ;;
      *) echo "Unsupported Linux arch: $ARCH" >&2; exit 1 ;;
    esac
    ;;
  *)
    echo "Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

URL="https://github.com/tailwindlabs/tailwindcss/releases/latest/download/${ASSET}"

mkdir -p bin
echo "Downloading ${ASSET} from ${URL}..."
curl -sSL -o bin/tailwindcss "$URL"
chmod +x bin/tailwindcss

echo "Installed: $(./bin/tailwindcss --help 2>&1 | head -1)"
