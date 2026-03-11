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
