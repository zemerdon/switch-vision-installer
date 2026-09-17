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

## Checking for updates

**Check for updates** actively refreshes the Switch Vision component sources before reporting what is current. Installer v2.1.41 no longer treats a successful legacy add-on reload as proof that the Home Assistant App Store refresh also succeeded: App Store refresh failures are surfaced instead of being masked as **No updates**.

The Installer then resolves the managed component versions from their authoritative release/repository sources and reports available updates. A failed source refresh is an update-check error, not evidence that the installed versions are current.

## Managed components

- Switch Vision custom integration
- Dashboard frontend and bundled visual assets
- Repository-backed Switch Vision Discovery, SNMP2MQTT, and optional UniFi2MQTT apps
- Discovery, SNMP2MQTT, and UniFi2MQTT Supervisor options
- Generated SNMP2MQTT YAML
- Calibration storage and custom logos/faceplates

Repository-managed app source trees are not copied from Switch Vision release ZIPs and are not restored from Installer backups.

## Release source

Switch Vision releases are read from:

`https://github.com/zemerdon/switch-vision-releases/releases/latest`

Expected installable asset naming:

`switch-vision-<version>.zip`
