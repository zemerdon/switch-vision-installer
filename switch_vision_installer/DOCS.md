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

## Updates

The Installer checks the public GitHub Latest release and selects an asset matching `switch-vision-*.zip`. It compares the available Switch Vision version with the installed integration version and offers an update or reinstall as appropriate.

## Safety

Before replacing managed files, the Installer can create and validate a backup. Published SHA-256 checksums are verified when available. Supported custom logos, faceplates, calibration data, app options, and generated SNMP2MQTT YAML are preserved or included in the backup workflow.

Backups are stored under `/share/switch-vision-backups/`. Existing backups under `/share/switch_vision/installer_backups/` remain available for compatibility.

## Managed components

- `/homeassistant/custom_components/switch_vision`
- `/homeassistant/www/switch-vision`
- Switch Vision Discovery app files and Supervisor options
- Switch Vision SNMP2MQTT app files and Supervisor options when supplied
- `/share/switch_vision/generated-snmp2mqtt.yaml`
- calibration data and supported custom assets

## Release requirements

The latest public GitHub release should include:

- `switch-vision-<version>.zip`
- a supported checksum asset such as `SHA256SUMS.txt` or a matching `.sha256` file

The GitHub release must be marked **Latest** for the default Installer configuration to detect it.
