# Switch Vision Installer v2.1.8

Official Home Assistant App for installing and updating Switch Vision from the public Switch Vision release repository.

The Installer is the only repository end users need to add manually. It installs the Switch Vision integration/frontend and manages the official Discovery, SNMP2MQTT, and optional UniFi2MQTT app repositories through Home Assistant Supervisor.

## v2.1.8

- Converts backup/restore fully to the repository-managed app model.
- Stops backing up or restoring Discovery/SNMP2MQTT local app source trees.
- Backs up and restores Discovery, SNMP2MQTT, and UniFi2MQTT Supervisor options.
- Keeps generated SNMP2MQTT YAML, calibration storage, custom assets, the Switch Vision custom integration, and dashboard frontend in the backup workflow.
- Stops copying SNMP2MQTT app source out of the main Switch Vision release ZIP.
- Adds GitHub Actions validation plus an offline backup/restore regression test.

## Managed components

- Switch Vision custom integration
- Dashboard frontend and visual assets
- Repository-backed Switch Vision Discovery
- Repository-backed Switch Vision SNMP2MQTT
- Optional repository-backed Switch Vision UniFi2MQTT
- Discovery, SNMP2MQTT, and UniFi2MQTT Supervisor options
- Generated SNMP2MQTT YAML
- Calibration storage and custom visual assets

New backups are stored under `/share/switch-vision-backups/`. Existing backups under `/share/switch_vision/installer_backups/` remain visible for compatibility, but legacy app source trees are not restored.

> Installer backups can contain saved app credentials inside Supervisor option JSON. Treat the backup directory as sensitive.

## UI preferences

The Installer reads density, text-size, and content-width preferences from `/share/switch_vision/ui-preferences.json`. Configure these values through the Switch Vision integration options.
