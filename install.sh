#!/usr/bin/env bash
# install.sh — one-shot installer for JARVIS Mark XXXIX on Linux / macOS.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/atxamov99/jarvis-agent/main/install.sh | bash
#
# Environment overrides:
#   JARVIS_HOME    — install directory (default: $HOME/jarvis-agent)
#   JARVIS_BRANCH  — branch to clone (default: main)
#   JARVIS_PYTHON  — python binary (default: python3)

set -euo pipefail

REPO_URL="${JARVIS_REPO_URL:-https://github.com/atxamov99/jarvis-agent.git}"
INSTALL_DIR="${JARVIS_HOME:-$HOME/jarvis-agent}"
BRANCH="${JARVIS_BRANCH:-main}"
PY_BIN="${JARVIS_PYTHON:-python3}"

# ── pretty output ─────────────────────────────────────────────────────────────
green()  { printf '\033[0;32m%s\033[0m\n' "$1"; }
yellow() { printf '\033[1;33m%s\033[0m\n' "$1"; }
red()    { printf '\033[0;31m%s\033[0m\n' "$1" >&2; }
blue()   { printf '\033[0;34m%s\033[0m\n' "$1"; }
step()   { printf '\n\033[1;36m▶ %s\033[0m\n' "$1"; }

die() { red "✗ $1"; exit 1; }

# ── detect OS ────────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Linux)  OS_NAME="linux" ;;
    Darwin) OS_NAME="macos" ;;
    *)      die "Unsupported OS: $OS (this script runs on Linux/macOS only)" ;;
esac

# ── header ───────────────────────────────────────────────────────────────────
cat <<'EOF'

     ╦  ╔═╗╦═╗╦  ╦╦╔═╗
     ║  ╠═╣╠╦╝╚╗╔╝║╚═╗
     ╝  ╩ ╩╩╚═ ╚╝ ╩╚═╝
     Mark-XXXIX — Voice AI Assistant

EOF
blue "Install target: $INSTALL_DIR"
blue "OS:             $OS_NAME"
blue "Python:         $PY_BIN"
echo ""

# ── 1. python ────────────────────────────────────────────────────────────────
step "Checking Python (>= 3.10 required)"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
    die "$PY_BIN not found. Install Python 3.10+ first: https://python.org"
fi

PY_VER="$("$PY_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJ="$(echo "$PY_VER" | cut -d. -f1)"
PY_MIN="$(echo "$PY_VER" | cut -d. -f2)"
if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt 10 ]; }; then
    die "Python $PY_VER is too old. Need Python 3.10 or newer."
fi
green "✓ Python $PY_VER"

# ── 2. system deps ───────────────────────────────────────────────────────────
step "Checking system dependencies"
MISSING_SYS=""

check_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        MISSING_SYS+="$1 "
    fi
}

check_cmd git
[ "$OS_NAME" = "linux" ] && check_cmd xdg-open
[ "$OS_NAME" = "linux" ] && check_cmd xhost

if [ -n "$MISSING_SYS" ]; then
    yellow "Missing system tools: $MISSING_SYS"
    yellow "On Ubuntu/Debian:  sudo apt install $MISSING_SYS portaudio19-dev"
    yellow "On Fedora:         sudo dnf install $MISSING_SYS portaudio-devel"
    yellow "On macOS:          brew install $MISSING_SYS portaudio"
    yellow "Continuing — but Jarvis may not work fully until these are installed."
fi

# ── 3. clone or update repo ──────────────────────────────────────────────────
step "Fetching JARVIS source"
if [ -d "$INSTALL_DIR/.git" ]; then
    yellow "$INSTALL_DIR exists — updating from $BRANCH"
    git -C "$INSTALL_DIR" fetch --quiet origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH" >/dev/null
else
    if [ -e "$INSTALL_DIR" ]; then
        die "$INSTALL_DIR exists but is not a git repo. Move or delete it first."
    fi
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi
green "✓ Source at $INSTALL_DIR"

# ── 4. virtualenv + python deps ──────────────────────────────────────────────
step "Creating Python virtualenv"
VENV="$INSTALL_DIR/venv"
if [ ! -d "$VENV" ]; then
    "$PY_BIN" -m venv "$VENV"
fi

VPIP="$VENV/bin/pip"
VPY="$VENV/bin/python"

"$VPIP" install --quiet --upgrade pip setuptools wheel
green "✓ Virtualenv ready"

step "Installing Python dependencies (this may take 2-3 minutes)"
REQ_FILE="$INSTALL_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    "$VPIP" install --quiet -r "$REQ_FILE"
    green "✓ Dependencies installed"
else
    yellow "No requirements.txt found — skipping"
fi

# ── 5. API key ───────────────────────────────────────────────────────────────
step "Configuring Gemini API key"
CONFIG_DIR="$INSTALL_DIR/config"
CONFIG_FILE="$CONFIG_DIR/api_keys.json"
mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_FILE" ] && grep -q '"gemini_api_key"' "$CONFIG_FILE" \
   && ! grep -q '"gemini_api_key": *""' "$CONFIG_FILE"; then
    green "✓ api_keys.json already contains a key — leaving it alone"
else
    if [ -t 0 ]; then
        echo ""
        yellow "A Gemini API key is required."
        yellow "Get one (free) at: https://aistudio.google.com/apikey"
        printf "Paste your Gemini API key (or press Enter to skip): "
        read -r GEMINI_KEY
    else
        GEMINI_KEY=""
        yellow "Non-interactive shell — skipping API-key prompt."
        yellow "Edit $CONFIG_FILE later to add your key."
    fi

    cat > "$CONFIG_FILE" <<JSON
{
    "gemini_api_key": "$GEMINI_KEY",
    "live_model": "",
    "os_system": "$OS_NAME"
}
JSON
    [ -n "$GEMINI_KEY" ] && green "✓ API key saved" || yellow "⚠ Key not set yet"
fi

# ── 6. shell command (`jarvis`) ──────────────────────────────────────────────
step "Adding 'jarvis' command to shell"

SHELL_RC=""
case "$(basename "${SHELL:-/bin/bash}")" in
    zsh)  SHELL_RC="$HOME/.zshrc" ;;
    bash) SHELL_RC="$HOME/.bashrc" ;;
    fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
    *)    SHELL_RC="$HOME/.profile" ;;
esac

JARVIS_FN_MARKER="# >>> jarvis-agent >>>"
JARVIS_FN_END="# <<< jarvis-agent <<<"

# Strip any old block
if [ -f "$SHELL_RC" ] && grep -q "$JARVIS_FN_MARKER" "$SHELL_RC"; then
    if [ "$OS_NAME" = "macos" ]; then
        sed -i '' "/$JARVIS_FN_MARKER/,/$JARVIS_FN_END/d" "$SHELL_RC"
    else
        sed -i "/$JARVIS_FN_MARKER/,/$JARVIS_FN_END/d" "$SHELL_RC"
    fi
fi

cat >> "$SHELL_RC" <<EOF

$JARVIS_FN_MARKER
jarvis() {
    "$VPY" "$INSTALL_DIR/main.py" "\$@"
}
$JARVIS_FN_END
EOF
green "✓ Added \`jarvis\` function to $SHELL_RC"

# ── 7. Linux: xhost autostart ────────────────────────────────────────────────
if [ "$OS_NAME" = "linux" ]; then
    step "Setting up X11 access for next session (Linux)"
    AUTOSTART="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART"
    DESKTOP_FILE="$AUTOSTART/jarvis-xhost.desktop"
    cat > "$DESKTOP_FILE" <<'EOF'
[Desktop Entry]
Type=Application
Name=Jarvis X11 Access
Comment=Grant local user access to X server for pyautogui (Jarvis-Agent)
Exec=sh -c "xhost +SI:localuser:$USER"
Terminal=false
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF
    # Apply immediately for this session too
    command -v xhost >/dev/null 2>&1 && xhost "+SI:localuser:$USER" >/dev/null 2>&1 || true
    green "✓ X11 autostart configured"
fi

# ── 8. done ──────────────────────────────────────────────────────────────────
echo ""
green "═══════════════════════════════════════════════════"
green " JARVIS Mark-XXXIX installed successfully!"
green "═══════════════════════════════════════════════════"
echo ""
yellow "To start using it:"
echo "  1. Open a new terminal (or run:  source $SHELL_RC)"
echo "  2. Type:                          jarvis"
echo ""
yellow "Installation directory: $INSTALL_DIR"
[ -z "${GEMINI_KEY:-}" ] && [ ! -s "$CONFIG_FILE" ] && \
    yellow "⚠ Remember to add your Gemini API key to $CONFIG_FILE"
echo ""
