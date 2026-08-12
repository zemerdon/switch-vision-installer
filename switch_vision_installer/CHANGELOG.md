# Changelog

## v2.1.8

- Converts Installer backup/restore to the repository-managed app model.
- Stops backing up or restoring Discovery and SNMP2MQTT local app source trees.
- Adds UniFi2MQTT Supervisor options to backup, validation metadata, listing, and restore.
- Keeps Discovery and SNMP2MQTT configuration backups while restoring them only through Supervisor.
- Stops copying SNMP2MQTT app source from the main Switch Vision release ZIP.
- Removes obsolete post-install instructions that treated SNMP2MQTT as a bundled local app.
- Adds GitHub Actions validation and an offline regression test for repository-era backup/restore behavior.
- Updates Installer documentation to describe repository-managed apps and sensitive option backups.

## v2.1.7

- Fixes legacy Discovery source cleanup on current Home Assistant Supervisor releases by using the `local_apps` mount at `/local_apps` instead of the deprecated `/addons` mount.
- Keeps `/addons/switch_vision_discovery` as a migration-only compatibility check for older installations.
- Removes stale local Discovery source files only after repository-backed Discovery is verified started.
- Reloads both local app metadata (`/addons/reload`) and App Store metadata (`/store/reload`) after cleanup.
- Verifies that `local_switch_vision_discovery` is no longer advertised by Supervisor before reporting a completed migration.
- Re-verifies the repository-backed Discovery app remains started after local metadata is refreshed.


## v2.1.6

- Fixes Discovery repository app detection by matching Home Assistant Supervisor's repository slug/namespace instead of assuming the store app reports the GitHub URL.
- Correctly recognises repository-backed Discovery slugs such as `3c82cf46_switch_vision_discovery`.
- Removes the false 120-second wait that occurred even when the Discovery repository and app were already visible in the Home Assistant App store.
- Makes Discovery repository setup and local-to-repository reconciliation mandatory for a successful Switch Vision install/reinstall.
- Refuses to report installation success unless the repository-backed Discovery app is installed, started, and matches the expected Supervisor store slug and published Discovery version.
- Keeps the existing safe migration order: preserve Discovery options, remove the legacy runtime without deleting configuration, install the repository app, restore options, start and verify it, then retire legacy local files.


## v2.1.5

- Moves Switch Vision Discovery from the bundled local `/addons` model to the official `switch-vision-discovery` Home Assistant App repository.
- Automatically registers the Discovery repository and installs or updates Discovery through Supervisor store endpoints.
- Migrates existing local Discovery installations without deleting their saved options, then restores configuration to the repository-backed app.
- Removes the legacy local Discovery source after migration so Supervisor no longer has competing local and repository copies.
- Stops requiring or copying Discovery from the main Switch Vision release ZIP; Discovery now versions independently.
- Keeps backup protection for Discovery configuration while no longer restoring legacy local Discovery source files.
- Clears stale previous success results when a new Installer operation begins.

## v2.1.4

- Refreshes both Supervisor app metadata and store metadata before deciding Discovery is stale.
- Uses the current Supervisor store endpoint for normal Discovery updates.
- Adds automatic stale-runtime recovery when newer Discovery files are present but Supervisor still reports the old version.
- Preserves Discovery options, removes the stale runtime without deleting its configuration, reinstalls Discovery, restores options, starts it, and verifies the expected version.
- Reduces the stale metadata wait before recovery so failed version reconciliation does not stall unnecessarily.

## v2.1.3

- Reconciles the running Switch Vision Discovery app with the Discovery version bundled in every Switch Vision install or reinstall.
- Fixes the Supervisor update endpoint used for Discovery updates.
- Repairs the partial-update case where current Discovery files exist in `/addons` but an older Discovery container is still running.
- Verifies the running Discovery version after update before reporting installation success.
- Preserves existing Discovery configuration while updating the app runtime.

## v2.1.2

- Moves UniFi2MQTT credentials and runtime configuration ownership to Switch Vision Hub.
- Removes the duplicate UniFi2MQTT configuration form from the Installer.
- Removes Installer-only UniFi configuration API endpoints and secret-handling code.
- Keeps UniFi2MQTT repository registration, installation, status reporting, and restart controls in the Installer.
- Directs users to Switch Vision Hub after installing UniFi2MQTT.
- Keeps UniFi2MQTT optional for installations that do not use UniFi switches.

## v2.1.1

- Adds an in-Installer UniFi2MQTT configuration card.
- Validates controller URL, Site ID, API key, MQTT host, port, polling interval, and topic prefixes before start.
- Saves UniFi2MQTT options through Home Assistant Supervisor and starts or restarts the add-on automatically.
- Never returns stored API keys or MQTT passwords to the browser; blank secret fields preserve existing saved secrets.
- Shows whether an API key or MQTT password is already saved without exposing its value.
- Keeps UniFi2MQTT optional for installations that do not use UniFi switches.

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
