#!/usr/bin/env bash
# One-time setup on a Raspberry Pi 5 (Raspberry Pi OS, 64-bit).
#   ./setup.sh              install everything and download the models
#   ./setup.sh --autostart  also start CogniSight when the Pi's desktop starts
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$1"; }

if [ "$(id -u)" = 0 ]; then
  echo "Run this as your normal user (without sudo). It asks for your password when it needs it."
  exit 1
fi

say "Installing system packages (needs your password)"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libportaudio2 espeak-ng curl
# The Pi camera library comes from Raspberry Pi OS, not from pip.
if ! sudo apt-get install -y python3-picamera2; then
  warn "python3-picamera2 is not available. The Pi camera will not work; a USB webcam still will."
fi

say "Creating the Python environment in .venv"
if [ ! -x .venv/bin/python ]; then
  # --system-site-packages lets the environment see Picamera2 from apt.
  python3 -m venv --system-site-packages .venv
fi
.venv/bin/python -m pip install --upgrade pip wheel

# Raspberry Pi OS Bookworm ships numpy 1.x, and Picamera2 is built against it.
# Installing numpy 2 into the environment breaks Picamera2, so keep 1.x there.
CONSTRAINTS="$(mktemp)"
SYSTEM_NUMPY="$(/usr/bin/python3 -c 'import numpy; print(numpy.__version__.split(".")[0])' 2>/dev/null || echo none)"
if [ "$SYSTEM_NUMPY" = "1" ]; then
  printf 'numpy<2\nopencv-contrib-python-headless<4.12\npandas<3\n' > "$CONSTRAINTS"
  echo "System numpy is 1.x; keeping numpy<2 so Picamera2 keeps working."
fi

say "Installing CogniSight, DeepFace, TensorFlow and speech (this takes 10 to 20 minutes)"
.venv/bin/pip install -c "$CONSTRAINTS" -e ".[faces,voice]"
rm -f "$CONSTRAINTS"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Put the Google Geolocation key in it to turn on location."
fi
mkdir -p data/faces

say "Downloading the face and speech models, so the demo works offline"
.venv/bin/cognisight download

say "Checking the camera"
if .venv/bin/cognisight camera --output camera-check.jpg; then
  echo "Saved camera-check.jpg. Open it to see what the camera sees."
else
  warn "The camera check failed. Check the ribbon cable (contacts facing the right way), then run: .venv/bin/cognisight camera"
fi

if [ "${1:-}" = "--autostart" ]; then
  say "Starting CogniSight automatically when the desktop starts"
  mkdir -p "$HOME/.config/autostart"
  cat > "$HOME/.config/autostart/cognisight.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=CogniSight
Exec=lxterminal -e "$PWD/start.sh"
X-GNOME-Autostart-enabled=true
EOF
  echo "Done. To turn this off, delete ~/.config/autostart/cognisight.desktop"
fi

say "Setup finished. Run ./start.sh"
