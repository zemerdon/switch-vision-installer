# Switch Vision Installer v2.0.1

Official Home Assistant App for installing and updating Switch Vision from the public Switch Vision release repository.

The Installer has its own version line. The Installer version identifies this app; the installed and available Switch Vision versions are shown separately in the Web UI.

## v2.0.1

- The main Install Switch Vision action now installs Discovery automatically when it is not already installed.
- The main Install Switch Vision action now installs SNMP2MQTT automatically when it is not already installed.
- Existing installed apps are left alone.
- Manual app-install buttons remain available for recovery.

## v2.0.0

- Automatically adds the official Switch Vision SNMP2MQTT Home Assistant App repository when required.
- Refreshes the App store and waits for SNMP2MQTT to become available.
- Ensures the repository is present before the separate SNMP2MQTT install action.
- Reports repository-registration failures without blocking the main Switch Vision installation.

## v1.9.11

- Adds simple left/right navigation to the in-app Switch Vision changelog viewer.
- Browses actual GitHub release history from the configured Switch Vision release API, newest first.
- Opens the current public release by default and disables navigation at the newest/oldest available entries.
- Loads release history only when the changelog is opened and caches it for the current Installer page session.
- Propagates the Home Assistant build version into the Installer runtime so the Web UI and request User-Agent stay aligned with the App version.

## v1.9.10

- Moves Release details above Components.

## v1.9.9

- Removes the Open Switch Vision block.
- Moves Backups to the bottom of the page.
- Adds persistent collapsible controls for Readiness checklist, Activity, and Backups.
- Automatically opens Activity while an operation is running.

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

Installer v2.0.1 reads its density, text-size, and content-width preferences from `/share/switch_vision/ui-preferences.json`. Configure these values through the Switch Vision integration options. Missing or invalid preferences fall back safely to Comfortable, Normal, and Standard.

