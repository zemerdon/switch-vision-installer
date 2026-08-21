# Changelog

## v2.1.24 — GitHub rate-limit-safe Core release discovery

- Stop using unauthenticated `api.github.com` requests for normal official Core version/status/install discovery.
- Resolve the latest public Core version through GitHub's standard `/releases/latest` redirect and deterministic release asset names.
- Continue requiring the exact `switch-vision-<version>.zip` asset and its published `.sha256` checksum before installation.
- Read the Core changelog from the public repository instead of the GitHub releases REST API.
- Preserve explicit custom release API support behind `allow_custom_release_source`; only opted-in custom sources use the structured API path.
- Prevent exhausted unauthenticated GitHub REST quotas from blocking normal Switch Vision update checks.

## v2.1.23 — Immutable Home Assistant base image

- Pin the Installer container to the resolved multi-architecture `ghcr.io/home-assistant/base` OCI index digest instead of the mutable `latest` tag.
- Preserve amd64 and arm64 platform selection through the pinned multi-arch manifest.
- Prevent future Installer rebuilds from silently consuming a different Home Assistant base image without an explicit source change.
- Preserve release-source trust enforcement, archive and HTTP limits, crash-atomic replacement, backup integrity, restore handling, and component management unchanged.

## v2.1.22 — Official release-source hardening

- Treat the official `zemerdon/switch-vision-releases` GitHub API endpoint as the only trusted Core release source by default.
- Reject a changed `release_api_url` before any network request unless `allow_custom_release_source` is explicitly enabled.
- Keep advanced/custom release-source support available as an intentional opt-in for development and recovery use.
- Preserve exact asset-name checks, trusted SHA-256 validation, archive limits, crash-atomic replacement, backup integrity, and component-manager behaviour unchanged.
- Add a regression proving untrusted release APIs are not contacted without explicit opt-in.

## v2.1.21 — Archive and ingress request hardening

- Adds strict release ZIP limits for archive entry count, individual uncompressed member size, total uncompressed size, and compression ratio.
- Keeps existing absolute-path, parent-traversal, and staging-boundary checks before extraction.
- Caps Installer JSON POST request bodies at 64 KiB.
- Rejects invalid or negative `Content-Length` values and malformed/non-object JSON with HTTP 400.
- Returns HTTP 413 for oversized request bodies.
- No changes to backup/restore semantics, crash-atomic Core replacement, Supervisor app migration, or release checksum verification.

## v2.1.20

- Replaces Core and dashboard frontend trees through same-directory staging and atomic rename promotion instead of deleting the live destination before copying the replacement.
- Writes a durable owner-only replacement transaction marker before moving the live tree, preserving enough state to recover from container, process, host, or power failure between rename operations.
- Recovers interrupted Core/frontend replacement transactions automatically when the Installer starts.
- Restores the previous tree for ordinary Python exceptions while preserving crash-recovery state if automatic rollback itself cannot complete.
- Validates transaction-marker paths before recovery and refuses symbolic-link or out-of-directory recovery targets.
- Adds regressions for successful replacement, staging-copy failure, crash after old-tree move, crash after new-tree promotion, first-install recovery, unsafe marker rejection, and startup recovery across both Installer-managed trees.
- Preserves the v2.1.19 checksum, backup-integrity, transactional restore, mutation-lock, and repository-backed component behavior unchanged.

## v2.1.19

- Requires a trusted SHA-256 for every Core install/update, using GitHub's release-asset `digest` when present and cross-checking a checksum asset when both are published.
- Requires the installable Core asset name to exactly match `switch-vision-<release-version>.zip`, verifies the downloaded byte count, and proves the packaged Core manifest version matches the GitHub release tag before replacing files.
- Removes the incorrect Discovery-version fallback from Core installed-version detection.
- Retries transient Home Assistant App Store publication/image races and reports a clear wait-and-retry message instead of surfacing a raw first-attempt 404/500.
- Verifies repository-backed Discovery, SNMP2MQTT, and UniFi2MQTT actually start at the version advertised by their public repository before reporting an update as successful.
- Reserves the Installer mutation lock before returning HTTP 202 and applies the same coordinator to backup deletion/pruning, app installs/restarts, Update Component, and Update All.
- Makes restore transactional: a private temporary safety snapshot captures current Core/frontend/calibration/generated YAML and app options, and is automatically restored if any restore step fails.
- Secures Installer backup directories/files to owner-only permissions because saved Supervisor options may contain credentials.
- Adds v2.1.19 regressions covering asset/digest identity, Core-version isolation, publication retry behaviour, mutation locking, private backup permissions, and transactional restore source guards.

## v2.1.18

- Removes the cancelled GitHub repository-rename migration from the component manager.
- Treats the existing public repository names as permanent: Core uses `switch-vision-releases`, while the SNMP2MQTT Home Assistant app uses `switch-vision-snmp2mqtt-addon`.
- Keeps the SNMP2MQTT engine source repository `switch-vision-snmp2mqtt` separate from the Home Assistant app repository.
- Removes the misleading **legacy repo alias active** labels and the obsolete `legacy_repository` component-status field.
- Keeps repository-backed install/update behaviour unchanged and continues validating the expected Home Assistant app layout.
- Updates Component Manager documentation to the permanent repository identities.
- Renames the v2.1.17-specific UI regression test to a version-independent test so it remains valid for future Installer releases.
- Changes GitHub Actions release validation from hard-coded version greps to config/backend/changelog consistency checks.

## v2.1.17

- Fixes stale System Actions controls so Discovery, SNMP2MQTT, and UniFi2MQTT install/restart buttons always follow the current Home Assistant Supervisor state.
- Fixes **Install UniFi2MQTT add-on** remaining visible when UniFi2MQTT is already installed.
- Keeps optional app install controls hidden until Supervisor status has been loaded, avoiding misleading startup-state actions.
- Adds a prominent **Restart Home Assistant Core required** action immediately after a Core install/update/reinstall changes the custom integration.
- Explains that new Core files can be on disk while Home Assistant is still running the previous integration version in memory until Core is restarted.
- Removes the redundant top **Core changelog** button; component changelogs remain beside each component in the Components section.
- Removes the obsolete changelog previous/next arrows and their separate history script; the full changelog remains available in the existing scrollable window.
- Adds regression checks for the v2.1.17 Installer UI/state cleanup.

## v2.1.16

- Prevents the running Installer from attempting to update its own Home Assistant app through Supervisor.
- Changes the Installer update action to **Update in Home Assistant** instead of issuing a self-update API request.
- Removes Installer from the executable **Update All** order and count.
- Keeps Installer version detection and its always-visible Changelog in the component manager.
- Adds a final required action when an Installer update is available after Update All.
- Makes the backend Installer update endpoint a safe no-op with Home Assistant App Store guidance, protecting against stale/cached frontends.
- Adds regression coverage for self-update safety.

## v2.1.15

- Marks an installed component as **Needs attention** when its minimum Switch Vision Core dependency is not satisfied instead of incorrectly showing **Up to date**.
- Shows both the required Core version and the currently installed Core version in the dependency warning.
- Treats an unmet dependency as an Update All dependency condition even when the dependent component itself is already at its latest version.
- Blocks Update All when no published Core can satisfy the requirement, and automatically clears the block when a compatible Core release is available.
- Clears stale Update All warning text after dependencies become healthy.
- Adds regression coverage for current-but-incompatible Discovery and compatible-Core recovery.

## v2.1.14

- Adds a central Switch Vision component manager to the Installer.
- Shows Switch Vision Core, Discovery, SNMP2MQTT, UniFi2MQTT, and Installer as independently versioned components.
- Keeps a **Changelog** button permanently visible for every component, including components that are already current.
- Adds per-component **Install/Update** actions through the Installer instead of requiring users to manage component repositories directly.
- Adds dependency-aware **Update All** in the safe order Core → Discovery → SNMP2MQTT → UniFi2MQTT → Installer.
- Protects Discovery v2.1.7+ from updating on Core versions older than v2.1.5; Update All upgrades Core first when a compatible Core release is available.
- Keeps optional UniFi2MQTT opt-in: Update All updates it only when it is already installed.
- Adds repository-name migration compatibility so old and new repository URLs can coexist during the rename.
- Defines the target component repository names `switch-vision-core`, `switch-vision-discovery`, `switch-vision-snmp2mqtt`, `switch-vision-unifi2mqtt`, and `switch-vision-installer`.
- Prevents the current SNMP2MQTT engine repository from being mistaken for the Home Assistant app repository by requiring the expected app `config.yaml` layout before selecting a repository.
- Keeps the existing Core backup/checksum/rollback path and Supervisor-managed app configuration preservation unchanged.

## v2.1.13

- Improves Discovery migration failure guidance during Switch Vision upgrades.
- Explains that a temporary Home Assistant App Store or newly published Discovery image can cause an installation retry to be required.
- Advises waiting about one minute and clicking **Reinstall** again; already-current components remain unchanged.
- Keeps the original Supervisor error visible and directs persistent failures to Supervisor logs.
- Adds regression coverage for the new recovery guidance.

## v2.1.12

- Fixes false-positive Custom component changes during dry-run after Home Assistant creates Python bytecode caches.
- Ignores `__pycache__`, `.pyc`, and `.pyo` runtime files when comparing managed component trees.
- Keeps real source-file differences detectable.
- Adds regression coverage proving runtime Python caches do not trigger reinstall recommendations.

## v2.1.11

- Fixes Discovery backup/restore metadata counting the Supervisor blank starter switch row as a configured switch.
- Counts only switch-list rows containing a real switch name or management host.
- Preserves legacy `devices` and `targets` list counting behaviour.
- Adds regression coverage for blank-only and blank-plus-configured Discovery switch lists.

## v2.1.10

- Adds **Restart Switch Vision Discovery** to required restore actions whenever Discovery configuration is restored.
- Shows safely skipped restore items in the Installer activity result instead of silently omitting them.
- Shows `UniFi2MQTT options: Not saved (not configured)` in backup metadata when the optional app is installed but setup is incomplete.
- Extends the backup/restore regression test to verify Discovery restart guidance and skipped UniFi handling.
- Adds JavaScript syntax validation to Installer CI.

## v2.1.9

- Fixes restore failure when optional UniFi2MQTT is installed but has never been configured.
- Treats Supervisor's default `site_id: null` / `api_key: null` UniFi options as unconfigured rather than as a restorable configuration.
- New backups omit unconfigured UniFi2MQTT defaults and record that UniFi configuration was skipped because setup is incomplete.
- Existing v2.1.8 backups containing unconfigured UniFi defaults remain valid and now restore successfully; the invalid UniFi option payload is skipped while the rest of the backup continues.
- Extends the repository backup regression test to cover both configured UniFi options and the exact unconfigured-default failure case found during live HaOS testing.

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
