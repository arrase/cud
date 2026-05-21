#!/usr/bin/env bash

set -e

echo "Starting Cud installation..."

# Check if running as root
if [ "$EUID" -eq 0 ]; then
  echo "Error: This script must not be run as root (or with sudo)."
  echo "Cud should be installed as a regular user."
  exit 1
fi

# Check for systemd
if ! command -v systemctl >/dev/null 2>&1 || [ ! -d "/run/systemd/system" ]; then
  echo "Error: A Linux distribution with systemd is required."
  echo "Cud relies on systemd to run agents as background services."
  exit 1
fi

# Define the repository URL
REPO_URL="git+https://github.com/arrase/cud.git"

# Check for pipx or uv
if command -v pipx >/dev/null 2>&1; then
  echo "Detected pipx. Installing/updating Cud from GitHub..."
  pipx install --force "$REPO_URL"
elif command -v uv >/dev/null 2>&1; then
  echo "Detected uv. Installing/updating Cud from GitHub..."
  uv tool install --force "$REPO_URL"
else
  echo "Error: Neither 'pipx' nor 'uv' is installed."
  echo "Please install one of them to proceed."
  echo ""
  echo "To install pipx (Ubuntu/Debian):"
  echo "  sudo apt update && sudo apt install pipx"
  echo ""
  echo "To install uv (Any Linux):"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# Setup Desktop Entry
echo "Setting up desktop application entry..."
mkdir -p "$HOME/.local/share/icons"
mkdir -p "$HOME/.local/share/applications"

ICON_URL="https://raw.githubusercontent.com/arrase/cud/main/src/cud/gui/assets/icon.png"
ICON_PATH="$HOME/.local/share/icons/cud.png"
DESKTOP_FILE="$HOME/.local/share/applications/cud.desktop"

echo "Downloading icon..."
curl -fsSL "$ICON_URL" -o "$ICON_PATH" || echo "Warning: Failed to download icon."

echo "Creating .desktop file..."
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=Cud
Comment=Local multi-agent framework
Exec=$HOME/.local/bin/cud-gui
Icon=cud
Terminal=false
Type=Application
Categories=Development;Utility;
EOF

# Update desktop database to refresh the applications menu
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" || true
fi

echo ""
echo "✨ Cud has been successfully installed!"
echo "You can now run 'cud --help' to get started."
