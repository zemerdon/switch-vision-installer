# Switch Vision Installer — Component Manager

Installer v2.1.14 introduces one lifecycle surface for the complete Switch Vision stack.

## Managed components

1. Switch Vision Core
2. Switch Vision Discovery
3. Switch Vision SNMP2MQTT
4. Switch Vision UniFi2MQTT (optional)
5. Switch Vision Installer

Each component exposes its installed version, latest repository version, current state, an always-visible Changelog button, and an Install/Update action when applicable.

`Update All` uses dependency order: Core → Discovery → SNMP2MQTT → UniFi2MQTT → Installer. Optional UniFi2MQTT is never installed implicitly.

## Repository rename migration

Target public component names:

- `switch-vision-releases` → `switch-vision-core`
- `switch-vision-snmp2mqtt` (engine source) → `switch-vision-snmp2mqtt-engine`
- `switch-vision-snmp2mqtt-addon` → `switch-vision-snmp2mqtt`
- `switch-vision-discovery` unchanged
- `switch-vision-unifi2mqtt` unchanged
- `switch-vision-installer` unchanged

The component manager accepts legacy aliases during migration. SNMP2MQTT repository detection validates the Home Assistant app layout before accepting the canonical name, avoiding the temporary name collision with the engine repository.

Normal users continue to add only `https://github.com/zemerdon/switch-vision-installer`.
