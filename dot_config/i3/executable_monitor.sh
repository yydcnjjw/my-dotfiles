#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

prev=$(xdpyinfo | awk '/dimensions/{print $2}')
while true; do
    cur=$(xdpyinfo | awk '/dimensions/{print $2}')
    if [ $cur != $prev ]
    then
       xmodmap $HOME/.Xmodmap
    fi
    sleep 2
done
