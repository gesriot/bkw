#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="${PYTHON_VERSION:-3.14}"
PRODUCT_NAME="${PRODUCT_NAME:-BKW}"
BUNDLE_ID="${BUNDLE_ID:-com.local.BKW}"
ARCH="${ARCH:-arm64}"
BUILD_ENV="${BUILD_ENV:-$ROOT_DIR/.build-venv/macos}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/dist/macos}"
DMG_ROOT="${DMG_ROOT:-$ROOT_DIR/dist/dmg-root}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.uv-cache}"
export NUITKA_CACHE_DIR="${NUITKA_CACHE_DIR:-$ROOT_DIR/.nuitka-cache}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT_DIR/.mplconfig}"

echo "==> Creating build environment: $BUILD_ENV"
uv venv --clear --python "$PYTHON_VERSION" "$BUILD_ENV"

VERSION="${VERSION:-$("$BUILD_ENV/bin/python" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
APP_PATH="$OUTPUT_DIR/main.app"
ICON_ICNS="$ROOT_DIR/dist/icons/$PRODUCT_NAME.icns"
ROUNDED_ICON="$ROOT_DIR/dist/icons/$PRODUCT_NAME-rounded.png"
DMG_PATH="$ROOT_DIR/dist/$PRODUCT_NAME-$VERSION-macos-$ARCH.dmg"

echo "==> Installing runtime dependencies into build environment"
env UV_PROJECT_ENVIRONMENT="$BUILD_ENV" uv sync --locked

echo "==> Installing build-only dependencies"
uv pip install --python "$BUILD_ENV/bin/python" "nuitka>=4,<5" ordered-set zstandard

NUITKA_ARGS=(
  --mode=app-dist
  --macos-app-name="$PRODUCT_NAME"
  --macos-signed-app-name="$BUNDLE_ID"
  --macos-app-version="$VERSION"
  --macos-app-mode=gui
  --macos-sign-identity=ad-hoc
  --macos-target-arch="$ARCH"
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
  --lto=yes
  --python-flag=-O
  --python-flag=no_docstrings
  --output-dir="$OUTPUT_DIR"
)

if [[ -f "$ROOT_DIR/icon.png" ]]; then
  echo "==> Generating rounded macOS icon from icon.png"
  "$BUILD_ENV/bin/python" scripts/make_icon.py \
    --input icon.png \
    --rounded-png "$ROUNDED_ICON" \
    --icns "$ICON_ICNS"
  NUITKA_ARGS+=(--macos-app-icon="$ICON_ICNS")
  NUITKA_ARGS+=(--include-data-files=icon.png=icon.png)
else
  echo "==> icon.png not found; building without a custom icon"
  NUITKA_ARGS+=(--macos-app-icon=none)
fi

echo "==> Removing previous macOS build output"
rm -rf "$APP_PATH" "$OUTPUT_DIR/main.build" "$OUTPUT_DIR/main.dist" "$DMG_ROOT" "$DMG_PATH"
mkdir -p "$OUTPUT_DIR"

echo "==> Building $PRODUCT_NAME.app with Nuitka"
"$BUILD_ENV/bin/python" -m nuitka "${NUITKA_ARGS[@]}" bkw_ui/main.py

# Nuitka --mode=app-dist names the bundle after the entry script (main.app).
# Rename to PRODUCT_NAME.app for distribution.
RENAMED_APP="$OUTPUT_DIR/$PRODUCT_NAME.app"
if [[ -d "$APP_PATH" && "$APP_PATH" != "$RENAMED_APP" ]]; then
  rm -rf "$RENAMED_APP"
  mv "$APP_PATH" "$RENAMED_APP"
  APP_PATH="$RENAMED_APP"
fi

echo "==> Verifying app signature"
codesign --verify --deep --strict "$APP_PATH"

echo "==> Creating DMG"
mkdir -p "$DMG_ROOT"
cp -R "$APP_PATH" "$DMG_ROOT/"
ln -s /Applications "$DMG_ROOT/Applications"
hdiutil create -volname "$PRODUCT_NAME" -srcfolder "$DMG_ROOT" -ov -format UDZO "$DMG_PATH"
hdiutil verify "$DMG_PATH"

echo "==> Done"
echo "App: $APP_PATH"
echo "DMG: $DMG_PATH"
