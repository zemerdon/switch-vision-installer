# Changelog

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
