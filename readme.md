# 🤖 MARK XXXIX (39)
### The Ultimate Cross-Platform Personal AI Assistant — By FatihMakes

> 📺 **[Watch the full setup video on YouTube](https://youtu.be/ej1f5OE3SNQ?si=lCxDhJix9ungq1Ry)**

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supporting Windows, macOS, and Linux. Local execution. Zero subscriptions. Engineered for total autonomy.

---

## ✨ Overview

MARK XXXIX represents the pinnacle of the Jarvis series, evolving into a more flexible and robust system. It bridges the gap between the operating system and human intent. Through natural dialogue, Mark 39 analyzes your screen, processes uploaded documents, and executes complex workflows with a brand-new, adaptive interface.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language |
| 🖥️ System Control | Launch apps, manage files, execute terminal commands |
| 🧩 Autonomous Tasks | High-level planning for complex, multi-step goals |
| 👁️ Visual Awareness | Real-time screen processing and webcam vision |
| 🧠 Persistent Memory | Deeply remembers your projects, preferences, and personal context |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |

---

## 🆕 What's New in XXXIX

- 📂 **Advanced File Handling** — New support for direct file uploads. Drop PDFs, source code, or images into the assistant to have them analyzed, summarized, or edited instantly.
- 🎨 **Adaptive & Flexible UI** — A complete overhaul of the interface. The new UI is fully resizable and responsive, featuring transparency controls and customizable layouts to fit your workspace perfectly.
- 🐧🍎 **Refined Cross-Platform Stability** — Major fixes for macOS and Linux compatibility. Core system actions are now more consistent across all three major operating systems.
- ⚡ **Optimized Core Engine** — Significant performance boost in tool-calling logic and response generation, resulting in a 40% faster interaction speed.

---

## ⚡ Quick Start — One-Line Install

**Linux / macOS:**

```bash
curl -sSL https://raw.githubusercontent.com/atxamov99/jarvis-agent/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://raw.githubusercontent.com/atxamov99/jarvis-agent/main/install.ps1 | iex
```

The installer will:
1. Check that Python 3.10+ and Git are installed
2. Clone the repo to `~/jarvis-agent` (or `$HOME\jarvis-agent` on Windows)
3. Create a virtualenv and install all dependencies
4. Prompt you for your free Gemini API key (https://aistudio.google.com/apikey)
5. Add a `jarvis` command to your shell
6. Configure X11 autostart (Linux) or a Desktop shortcut (Windows)

After install, open a new terminal and just type `jarvis` to launch.

### Customize the install
```bash
JARVIS_HOME=/opt/jarvis JARVIS_BRANCH=yahyo bash install.sh
```
Override variables: `JARVIS_HOME` (install dir), `JARVIS_BRANCH` (git branch), `JARVIS_PYTHON` (python binary).

---

## 🛠️ Manual Install

If you'd rather do it by hand:

```bash
git clone https://github.com/atxamov99/jarvis-agent.git
cd jarvis-agent
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
# Edit config/api_keys.json — add your Gemini API key
python main.py
```

> ⚠️ **Note:** Some OS-specific dependencies aren't in `requirements.txt`. If you hit `ModuleNotFoundError`, install the missing package via `pip install <module_name>`.

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Key** | Free Gemini API key |

---

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Connect with the Creator

Engineered by a developer building a real-world JARVIS-style assistant.
⭐ **Star the repository to support the journey to Mark 100.**

| Platform | Link |
|---|---|
| YouTube | [@FatihMakes](https://www.youtube.com/@FatihMakes) |
| Instagram | [@fatihmakes](https://www.instagram.com/fatihmakes) |
