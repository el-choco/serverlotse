#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Bitte mit sudo ausführen.'; exit 1; }
target=/run/serverlotse-system
mkdir -p "$target"
if mountpoint -q "$target"; then
    echo 'Systemansicht bereits eingehängt; keine weitere Einhängung erstellt.'
else
    mount --bind / "$target"
fi
root_device=$(findmnt -n -o MAJ:MIN -T /)
view_device=$(findmnt -n -o MAJ:MIN -T "$target")
[ "$root_device" = "$view_device" ] || { echo 'Falscher Datenträger in der Systemansicht. Abbruch.'; exit 1; }
mount -o remount,bind,ro "$target"
echo 'Schreibgeschützte Systemansicht bereit:'
findmnt "$target"
