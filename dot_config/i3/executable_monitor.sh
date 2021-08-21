#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

echo $(xdpyinfo | awk '/dimensions/{print $2}') > /tmp/.monitor_watch

while true; do
    prv=$(cat /tmp/.monitor_watch)
    cur=$(xdpyinfo | awk '/dimensions/{print $2}')
    if [ $cur != $prev ]
    then
       xmodmap $HOME/.Xmodmap
    fi
    sleep 2
done
