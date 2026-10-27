#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Bitte mit sudo ausführen.'; exit 1; }
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -D -m 0755 "$script_dir/prepare-host.sh" /usr/local/lib/serverlotse/prepare-host.sh
install -m 0644 "$script_dir/serverlotse-view.service" /etc/systemd/system/serverlotse-view.service
systemctl daemon-reload
systemctl enable --now serverlotse-view.service
echo 'Systemansicht ist für den nächsten Start eingerichtet.'
