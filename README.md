# Switch Vision Installer Repository

This is the official Home Assistant App repository for the Switch Vision Installer.

## Install

1. In Home Assistant, open **Settings → Apps → App store**.
2. Open the three-dot menu and choose **Repositories**.
3. Add:

   `https://github.com/zemerdon/switch-vision-installer`

4. Install **Switch Vision Installer**.
5. Start the app and open its Web UI.
6. Run **Dry run**, then **Install Switch Vision**.

After the repository is added, the Installer is the only manual installation path required. It downloads the current Switch Vision release, verifies it, backs up the existing installation when required, installs or updates the managed components, and preserves supported user data.

## Managed components

- Switch Vision custom integration
- Dashboard frontend and bundled visual assets
- Switch Vision Discovery app
- Switch Vision SNMP2MQTT app when included in the release
- Discovery and SNMP2MQTT options
- Generated SNMP2MQTT YAML
- Calibration storage and custom logos/faceplates

## Release source

Switch Vision releases are read from:

`https://github.com/zemerdon/switch-vision-releases/releases/latest`

Expected installable asset naming:

`switch-vision-<version>.zip`
