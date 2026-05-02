#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="${PYTHON_VERSION:-3.14}"
PRODUCT_NAME="${PRODUCT_NAME:-BKW}"
ARCH="${ARCH:-x64}"
BUILD_ENV="${BUILD_ENV:-$ROOT_DIR/.build-venv/linux}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/dist/linux}"
LTO="${LTO:-yes}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.uv-cache}"
export NUITKA_CACHE_DIR="${NUITKA_CACHE_DIR:-$ROOT_DIR/.nuitka-cache}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT_DIR/.mplconfig}"

echo "==> Creating build environment: $BUILD_ENV"
uv venv --clear --python "$PYTHON_VERSION" "$BUILD_ENV"

VERSION="${VERSION:-$("$BUILD_ENV/bin/python" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
DIST_PATH="$OUTPUT_DIR/main.dist"
TAR_PATH="$ROOT_DIR/dist/$PRODUCT_NAME-$VERSION-linux-$ARCH.tar.gz"

echo "==> Installing runtime dependencies into build environment"
env UV_PROJECT_ENVIRONMENT="$BUILD_ENV" uv sync --locked

echo "==> Installing build-only dependencies"
uv pip install --python "$BUILD_ENV/bin/python" "nuitka>=4,<5" ordered-set zstandard

echo "==> Removing previous Linux build output"
rm -rf "$DIST_PATH" "$OUTPUT_DIR/main.build" "$TAR_PATH"
mkdir -p "$OUTPUT_DIR"

NUITKA_ARGS=(
  --mode=standalone
  --enable-plugin=pyside6
  --include-package=bkw_py
  --include-package=bkw_ui_app
  --include-package=pyqtgraph
  --include-package=numpy
  --include-module=PySide6.QtOpenGL
  --include-module=PySide6.QtOpenGLWidgets
  --include-package-data=bkw_py
  --include-package-data=pyqtgraph
  --include-package-data=numpy
  --include-data-dir="$ROOT_DIR/bkw_ui/tdf_engine=tdf_engine"
  --assume-yes-for-downloads
  --lto="$LTO"
  --python-flag=-O
  --python-flag=no_docstrings
  --output-filename="$PRODUCT_NAME"
  --output-dir="$OUTPUT_DIR"
)

if [[ -f "$ROOT_DIR/icon.png" ]]; then
  NUITKA_ARGS+=(--include-data-files=icon.png=icon.png)
fi

echo "==> Building Linux application with Nuitka"
"$BUILD_ENV/bin/python" -m nuitka "${NUITKA_ARGS[@]}" bkw_ui/main.py

if [[ ! -x "$DIST_PATH/$PRODUCT_NAME" ]]; then
  echo "Expected executable was not created: $DIST_PATH/$PRODUCT_NAME" >&2
  exit 1
fi

# Rename the dist directory inside the tarball so it extracts to BKW.dist/
RENAMED_DIST="$OUTPUT_DIR/$PRODUCT_NAME.dist"
if [[ "$DIST_PATH" != "$RENAMED_DIST" ]]; then
  rm -rf "$RENAMED_DIST"
  mv "$DIST_PATH" "$RENAMED_DIST"
fi

echo "==> Creating TAR artifact"
tar -C "$OUTPUT_DIR" -czf "$TAR_PATH" "$PRODUCT_NAME.dist"

echo "==> Done"
echo "Dist: $RENAMED_DIST"
echo "TAR:  $TAR_PATH"
