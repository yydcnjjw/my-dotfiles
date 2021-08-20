#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

sudo pacman -S --needed --noconfirm i3-gaps i3lock dmenu picom dunst alacritty tmux fcitx5 fcitx5-rime fcitx5-mozc fcitx5-qt fcitx5-gtk

if [ ! -d $HOME/.oh-my-zsh/ ]
then
    sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
fi

# TODO: polybar(aur)
