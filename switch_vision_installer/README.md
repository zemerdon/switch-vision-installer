# Switch Vision Installer — installation and update notes

This Home Assistant app installs Switch Vision Core and manages the separately versioned Discovery/Hub, SNMP2MQTT and optional UniFi2MQTT apps. The public Installer repository is a customer distribution channel; canonical engineering source, development validation and release decisions remain on local `sv-dev` infrastructure.

The actual app version is defined by `config.yaml`, not by a fixed README title. For a normal installation, add only the public Switch Vision Installer repository; the Installer manages the other component repositories.

For normal updates, use the Installer's checked installed/latest component versions and dependency-aware workflow. Installer self-updates remain Home Assistant Supervisor actions. Never assume an installation succeeded or failed merely because its request timed out: check Supervisor's settled version and running state before another install/reinstall. Preserve existing options, backups and per-switch Calibration unless a specific reviewed action says otherwise.

## Historical release notes

The versioned sections below are preserved change history, not a current command sequence or a claim that the current app is still at the older version. Consult the installed app, current documentation and Home Assistant Supervisor state for present-day recovery and retry decisions.

## v2.1.19

- Verifies the exact versioned Core asset and a trusted SHA-256 before installation.
- Retries temporary Home Assistant App Store image-publication races.
- Serializes all Installer mutations and makes backup restore transactional.
- Keeps credential-bearing backups owner-only.

## v2.1.16

- Prevents unsupported Installer self-update attempts from inside the running Installer app.
- Installer updates remain visible with version/changelog information but are applied from Home Assistant Settings → Apps.
- Update All manages Core, Discovery, SNMP2MQTT, and installed UniFi2MQTT only, then reports any Installer update as a final action.

## v2.1.15

- Shows **Needs attention** for installed components whose Core dependency is not satisfied.
- Includes installed and required Core versions in dependency warnings.
- Makes Update All dependency-aware even when the dependent component itself is already current.
- Clears dependency warnings automatically once a compatible Core is available/installed.


## v2.1.14

- Adds one component-management view for Core, Discovery, SNMP2MQTT, UniFi2MQTT, and Installer.
- Keeps Changelog permanently visible for every component.
- Adds per-component Install/Update actions and dependency-aware Update All.
- Preserves legacy repository aliases during the component-repository rename.
- Keeps normal users on the single `switch-vision-installer` repository path.



## v2.1.13

- Discovery migration failures now explain the safe retry procedure directly in the Installer.
- Wait about one minute and click **Reinstall** again when a temporary Supervisor/App Store failure occurs.
- Components that are already current are left unchanged during the retry.
- Persistent failures still show the original Supervisor error for troubleshooting.




## v2.1.12

- Dry-run ignores Python runtime cache files created by Home Assistant.
- `__pycache__`, `.pyc`, and `.pyo` files no longer make a current Switch Vision component appear changed.
- Real managed-file differences are still detected normally.


## v2.1.11

- Discovery backup and restore summaries no longer count the blank Supervisor starter row as a configured switch.
- Configured switch totals now reflect real Discovery switch entries only.
- Regression coverage protects blank and populated switch-list handling.

## v2.1.10

- Restore results now include a Discovery restart whenever Discovery options were restored.
- Safely skipped restore items are shown in the UI.
- Backup metadata distinguishes an unconfigured optional UniFi2MQTT app from a saved UniFi configuration.
- CI now syntax-checks the Installer frontend JavaScript.

## v2.1.9

- Skips invalid default UniFi2MQTT options when the optional app is installed but not configured.
- New backups only mark UniFi2MQTT configuration as saved when all required Supervisor options are populated.
- Existing v2.1.8 backups with `site_id: null` / `api_key: null` restore successfully without blocking the rest of the recovery.

## v2.1.8

- Converts backup/restore fully to the repository-managed app model.
- Stops backing up or restoring Discovery/SNMP2MQTT local app source trees.
- Backs up and restores Discovery, SNMP2MQTT, and UniFi2MQTT Supervisor options.
- Keeps generated SNMP2MQTT YAML, calibration storage, custom assets, the Switch Vision custom integration, and dashboard frontend in the backup workflow.
- Stops copying SNMP2MQTT app source out of the main Switch Vision release ZIP.
- Adds GitHub Actions validation plus an offline backup/restore regression test.

## Managed components

- Switch Vision custom integration
- Dashboard frontend and visual assets
- Repository-backed Switch Vision Discovery
- Repository-backed Switch Vision SNMP2MQTT
- Optional repository-backed Switch Vision UniFi2MQTT
- Discovery, SNMP2MQTT, and UniFi2MQTT Supervisor options
- Generated SNMP2MQTT YAML
- Calibration storage and custom visual assets

New backups are stored under `/share/switch-vision-backups/`. Existing backups under `/share/switch_vision/installer_backups/` remain visible for compatibility, but legacy app source trees are not restored.

> Installer backups can contain saved app credentials inside Supervisor option JSON. Treat the backup directory as sensitive.

## UI preferences

The Installer reads density, text-size, content-width, and the selected shared management theme from `/share/switch_vision/ui-preferences.json`. Configure density/size/width through Switch Vision settings and build/select named custom themes from **Switch Vision Settings → Custom Theme** in Discovery / Hub. The same sanitized palette is applied across Discovery and Installer; dashboard/card/faceplate presentation is unaffected.
