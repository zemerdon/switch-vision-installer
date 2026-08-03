# Switch Vision Installer v1.9.8

Official Home Assistant App for installing and updating Switch Vision from the public Switch Vision release repository.

The Installer has its own version line. The Installer version identifies this app; the installed and available Switch Vision versions are shown separately in the Web UI.

## v1.9.8

- Places Activity immediately above Backups.
- Adds an in-app changelog viewer for the latest Switch Vision GitHub release.

## v1.9.7

- Repository-ready Home Assistant App packaging.
- Direct installation after adding the official GitHub repository to the Home Assistant App Store.
- Installer is now the single user-facing path for clean installs and updates.
- Current multi-architecture Home Assistant base image and app labels.
- Stable release stage.
- Preserves dry-run validation, checksums, backups, restore, release detection, and custom assets.
- Automatically applies and verifies versioned Switch Vision Discovery updates through Supervisor.
- Uses a compact Installer interface with reduced typography and spacing for better information density.

## Managed components

- Switch Vision custom integration
- Dashboard frontend and visual assets
- Switch Vision Discovery
- Switch Vision SNMP2MQTT when packaged by the selected release
- Discovery and SNMP2MQTT Supervisor options
- Generated SNMP2MQTT YAML
- Calibration storage and custom visual assets

New backups are stored under `/share/switch-vision-backups/`. Existing backups under `/share/switch_vision/installer_backups/` remain visible and restorable.
## UI preferences

Installer v1.9.8 reads its density, text-size, and content-width preferences from `/share/switch_vision/ui-preferences.json`. Configure these values through the Switch Vision integration options. Missing or invalid preferences fall back safely to Comfortable, Normal, and Standard.

