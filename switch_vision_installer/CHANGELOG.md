# Changelog

## v2.1.0

- Adds optional Switch Vision UniFi2MQTT management to the Installer.
- Registers the official `switch-vision-unifi2mqtt` Home Assistant App repository on demand.
- Installs UniFi2MQTT through Home Assistant Supervisor from the Installer UI.
- Detects and reports UniFi2MQTT availability, installed version, and runtime state.
- Adds manual Install and Restart UniFi2MQTT recovery actions.
- Keeps UniFi2MQTT optional so non-UniFi Switch Vision installations are not blocked.
- Updates the Installer Home Assistant map declaration from legacy `addons` to `local_apps`.

## v2.0.1

- Automatically installs Switch Vision Discovery when the main installation finds it missing.
- Automatically installs Switch Vision SNMP2MQTT when the main installation finds it missing.
- Leaves already-installed Discovery and SNMP2MQTT apps untouched.
- Keeps the individual Install Discovery and Install SNMP2MQTT controls as manual recovery actions.
- Reports automatic app-install failures as warnings without discarding an otherwise successful Switch Vision file installation.


## v2.0.0

- Aligns the Installer release line with Switch Vision 2.x.
- Automatically registers the official `switch-vision-snmp2mqtt-addon` repository when SNMP2MQTT is not already available.
- Reloads the Home Assistant App store and waits for Switch Vision SNMP2MQTT to become discoverable.
- Makes the standalone SNMP2MQTT install action ensure the repository exists first.
- Keeps repository-registration failure non-blocking for the main Switch Vision installation and reports it as a warning.


## v1.9.11

- Adds simple left/right navigation to browse previous and newer Switch Vision GitHub release changelogs.
- Uses the configured release API repository as the changelog-history source.
- Keeps the current public release as the default changelog view.
- Loads and caches release history only when the changelog panel is opened.
- Aligns the Installer runtime version with the Home Assistant build version.

## v1.9.10

- Moves Release details above Components in the Installer UI.

## v1.9.9

- Removes the Open Switch Vision launch block from the Installer UI.
- Moves Backups to the bottom of the Installer page.
- Makes Readiness checklist, Activity, and Backups collapsible.
- Remembers each collapsible section state in the browser.
- Automatically expands Activity while an operation is running.

## v1.9.8

- Moves the Activity panel directly above Backups so installation and backup progress remain close to the related controls.
- Adds a Show changelog button beside the latest Switch Vision release version.
- Displays the latest GitHub release notes in a safe, expandable Installer panel.
- Keeps release installation available when release notes are empty or unavailable.

## v1.9.7

- Reads shared Installer UI preferences from `/share/switch_vision/ui-preferences.json`.
- Supports Comfortable, Compact, and Dense spacing modes.
- Supports Normal and Small text sizes.
- Supports Standard, Wide, and Full content widths.
- Validates all preference values and safely falls back to Comfortable / Normal / Standard when the file is missing or invalid.
- Applies preferences whenever the Installer web interface is opened or refreshed.

## v1.9.7

- Reduces Installer typography across titles, cards, controls, status rows, and activity output.
- Tightens card padding, vertical spacing, component rows, checklists, and backup controls.
- Increases the usable content width slightly so more information fits on screen.
- Keeps the existing layout, colours, behaviour, and mobile responsiveness unchanged.

## v1.9.5

- Handles Discovery updates that complete with the app stopped.
- Waits for the expected Discovery version first, then starts the app when necessary.
- Verifies the final Discovery version and running state before reporting success.
- Prevents the installer from remaining at 90% after a successful Supervisor update.

## v1.9.4

- Uses Home Assistant Supervisor's normal app update endpoint for versioned Discovery updates.
- Refreshes local app metadata and waits for Supervisor to advertise the new Discovery version.
- Updates Discovery automatically, waits for it to restart, and verifies the installed version.
- Includes Supervisor error response details in installer failures.
- Replaces the unsuccessful forced rebuild workflow introduced in v1.9.3.

## v1.9.3

- Automatically refreshes local app metadata after installing new Discovery source files.
- Stops, rebuilds, starts, and verifies Switch Vision Discovery when the bundled version changes.
- Preserves Supervisor-managed Discovery options during the rebuild.
- Refuses to report a fully successful update unless the installed Discovery version matches the release package.
- Reduces post-update guidance to running Discovery when the automatic rebuild succeeds.

## v1.9.1

- Updated Switch Vision release validation for the current `local_apps/` layout.
- Updated Discovery package detection to use `local_apps/switch_vision_discovery`.
- Updated SNMP2MQTT package detection to use `local_apps/switch_vision_snmp2mqtt`.
- Removed downloaded-release assumptions that required the old `addons/` folder.
- Updated the installer interface version fallback to v1.9.1.

## 1.9.0

- Converts the Installer into a complete Home Assistant App repository package.
- Adds root `repository.yaml` metadata for direct App Store repository installation.
- Makes the repository-installed Installer the single user-facing installation and update path for Switch Vision.
- Updates the container build to use the current multi-architecture Home Assistant base image explicitly.
- Adds current Home Assistant app image labels.
- Promotes the Installer app from experimental to stable.
- Adds repository installation, first-install, update, backup, restore, and release-asset documentation.
- Retains GitHub Latest release detection, SHA-256 verification, dry-run checks, backups, rollback support, and custom-asset preservation.

## 1.8.10

- Fixed Discovery and SNMP2MQTT launch buttons on current Home Assistant versions.
- Uses the current Home Assistant app-details route with the Supervisor-reported app slug.
