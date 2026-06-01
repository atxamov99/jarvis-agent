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
step "Installing system dependencies"
# Tools the feature set relies on: window/input control, silent+flash screenshots,
# media control, audio, PDF text, desktop notifications.
if [ "$OS_NAME" = "linux" ]; then
    APT_PKGS="git xdotool ydotool wtype gnome-screenshot playerctl wmctrl ffmpeg poppler-utils libnotify-bin xdg-utils x11-xserver-utils portaudio19-dev python3-venv"
    if command -v apt-get >/dev/null 2>&1; then
        yellow "Installing via apt (sudo password may be required)..."
        sudo apt-get update -qq 2>/dev/null || true
        sudo apt-get install -y $APT_PKGS 2>/dev/null && green "✓ System tools installed" \
            || yellow "⚠ Some apt packages failed — install manually: sudo apt install $APT_PKGS"
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y git xdotool ydotool wtype gnome-screenshot playerctl wmctrl ffmpeg poppler-utils libnotify portaudio-devel 2>/dev/null \
            && green "✓ System tools installed" || yellow "⚠ Install manually with dnf."
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm git xdotool ydotool wtype gnome-screenshot playerctl wmctrl ffmpeg poppler libnotify portaudio 2>/dev/null \
            && green "✓ System tools installed" || yellow "⚠ Install manually with pacman."
    else
        yellow "Unknown package manager — install manually: $APT_PKGS"
    fi
else  # macOS
    if command -v brew >/dev/null 2>&1; then
        yellow "Installing via Homebrew..."
        brew install git playerctl ffmpeg poppler portaudio 2>/dev/null || true
        green "✓ Homebrew tools installed (screenshot/window control are native on macOS)"
    else
        yellow "Homebrew not found. Install it from https://brew.sh, then: brew install git ffmpeg poppler portaudio"
    fi
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
    "openai_api_key": "",
    "anthropic_api_key": "",
    "groq_api_key": "",
    "backend": "auto",
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
