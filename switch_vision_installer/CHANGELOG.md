# Changelog

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
