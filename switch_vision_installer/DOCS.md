# Switch Vision Installer

The Switch Vision Installer is the supported installation and update path for Switch Vision on Home Assistant OS.

## First installation

1. Add the official Switch Vision Installer repository to the Home Assistant App Store.
2. Install and start **Switch Vision Installer**.
3. Open the Web UI.
4. Select **Check for updates**.
5. Run **Dry run** and review all preflight checks.
6. Select **Install Switch Vision** after the dry run succeeds.
7. Follow the post-install actions shown by the Installer.

The Installer repository is the only repository users need to add manually. Discovery, SNMP2MQTT, and optional UniFi2MQTT are registered and managed by the Installer.

## Updates

The Installer checks the public GitHub Latest release and selects an asset matching `switch-vision-*.zip`. It compares the available Switch Vision version with the installed integration version and offers an update or reinstall as appropriate.

Repository-managed apps version independently from the main Switch Vision release. Their source trees are not copied from the Switch Vision release ZIP.

## Safety and backups

Before replacing managed Switch Vision files, the Installer can create and validate a backup. Published SHA-256 checksums are verified when available.

Current backups include:

- Switch Vision custom integration
- Dashboard frontend and supported visual assets
- Discovery Supervisor options
- SNMP2MQTT Supervisor options
- UniFi2MQTT Supervisor options when installed/configured
- generated SNMP2MQTT YAML
- calibration storage

Repository-managed app source trees are deliberately excluded. Restore reapplies app options to the installed repository-backed apps rather than recreating local apps.

Backups are stored under `/share/switch-vision-backups/`. Existing backups under `/share/switch_vision/installer_backups/` remain available for compatibility.

**Security:** app option backups can contain credentials such as SNMP communities, MQTT credentials, or UniFi API keys. Keep the backup directory private.

## Release requirements

The latest public GitHub Switch Vision release should include:

- `switch-vision-<version>.zip`
- a supported checksum asset such as `SHA256SUMS.txt` or a matching `.sha256` file

The main release ZIP no longer needs to package Discovery, SNMP2MQTT, or UniFi2MQTT app source.

## UI preferences

The Installer reads density, text-size, and content-width preferences from `/share/switch_vision/ui-preferences.json`. Configure these values through the Switch Vision integration options.
