#!/usr/bin/with-contenv bashio
set -euo pipefail

export SV_INSTALLER_OPTIONS=/data/options.json
export SV_INSTALLER_STATE=/data/state.json
export SV_INSTALLER_WORK=/data/work
export SV_INSTALLER_BACKUPS=/share/switch-vision-backups
export SV_INSTALLER_WEB=/opt/switch-vision-installer/www
mkdir -p "$SV_INSTALLER_WORK" "$SV_INSTALLER_BACKUPS"

exec python3 /opt/switch-vision-installer/app/web.py
