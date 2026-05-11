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

- `local-notify`: runs `notify-send` on the destination desktop machine's local session.
- `remote-notify`: connects over `SSH` and asks the destination machine to run `local-notify`.

### Desktop Host Requirements

The destination desktop machine needs:

- `notify-send`
- an active user session with the usual user bus at `/run/user/<uid>/bus`
- `local-notify` installed from this repo

`local-notify` only exports `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` for the local user session before running `notify-send`. It does not expose the full session bus directly over the network.

### Remote Setup

On the remote shell where you want to send notifications back to your desktop, make sure `remote-notify` is installed and point `REMOTE_NOTIFY_HOST` at the desktop machine that should display them:

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
