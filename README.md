# Dotfiles

My dotfiles managed by [chezmoi](https://www.chezmoi.io/).

## Managed Files

- **Git**: `.gitconfig`
- **Tmux**: `.tmux.conf`
- **Zsh**: `.zshenv`, `.zshrc`

## Quick Start

1. Install `chezmoi`.
2. Initialize and apply:

```bash
chezmoi init --apply <your-github-username>
```

## Usage

Edit a file:

```bash
chezmoi edit ~/.zshrc
```

Apply changes:

```bash
chezmoi apply
```

## Remote Notifications

This repo includes two notification helpers:

- `local-notify`: displays a notification on the current machine. On Linux desktops it runs `notify-send` with the active user session bus; on WSL2 it sends a Windows toast notification through PowerShell.
- `remote-notify`: connects over `SSH` and asks the destination machine to run `local-notify`.

### Desktop Host Requirements

The destination desktop machine needs `local-notify` installed from this repo.

Linux desktop targets also need:

- `notify-send`
- an active user session with the usual user bus at `/run/user/<uid>/bus`

WSL2 targets need a usable Windows PowerShell path. BurntToast is optional; without it, `local-notify` falls back to Windows Forms.

`local-notify` only exports `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` for the local user session before running `notify-send`. It does not expose the full session bus directly over the network.

### Remote Setup

On the sending machine, install `remote-notify` from this repo and point `REMOTE_NOTIFY_HOST` at the desktop machine that should display notifications. On that desktop target, install `local-notify` from this repo:

```bash
export REMOTE_NOTIFY_HOST="your-desktop"
```

Authentication and transport are handled by `SSH`, so your remote environment must already be able to connect to that host.

### Send A Notification

Call `remote-notify` from the remote machine:

```bash
remote-notify "build finished" "all tasks passed"
```

You can also override the target host for one call:

```bash
remote-notify --host "your-desktop" "deploy complete"
```

### `notify-send` Compatibility Layer

`dot_zshrc.tmpl` defines a shell `notify-send` function when `remote-notify` is available.

- If `REMOTE_NOTIFY_HOST` is set, `notify-send ...` forwards to `remote-notify`.
- If `REMOTE_NOTIFY_HOST` is not set, it falls back to the original local `notify-send` binary.

This keeps normal local notifications working while letting the same `notify-send` command route through the remote wrapper when the environment variable is present.

Gemini and OpenCode notification hooks use the same routing rule directly: if `REMOTE_NOTIFY_HOST` is non-empty and `remote-notify` is available they call `remote-notify`, otherwise they call `local-notify`. This avoids relying on interactive shell functions in non-interactive hook processes.

### Notification Voice

`local-notify` can play a short Japanese voice message before showing the text notification. The voice is generated on the machine that displays the notification, so `remote-notify` automatically plays audio on the destination desktop host.

Voice support uses `notify-voice`, GitHub Models API, and a local HTTP TTS service. Configure `GITHUB_TOKEN` on the desktop host for text polishing. The TTS request defaults to `http://localhost:8000/tts` and sends `{"text": "...", "lang": "Japanese", "translate": false}`. If the GitHub Models request fails, the spoken fallback is `通知があります`.

`local-notify` still shows the text notification even if `notify-voice` succeeds or fails.

Useful environment variables:

- `NOTIFY_VOICE_ENABLED=0`: disable voice playback.
- `NOTIFY_VOICE_TIMEOUT=20`: maximum seconds `local-notify` waits for voice playback before showing the text notification.
- `NOTIFY_VOICE_TEXT_MODEL=gpt-4o-mini`: GitHub Models text model.
- `NOTIFY_VOICE_TTS_URL=http://localhost:8000/tts`: local TTS service URL.

Generated audio is cached under `${XDG_CACHE_HOME:-~/.cache}/notify-voice/` as `wav` files. The cache keeps at most 50 files and removes the least recently used files first.
