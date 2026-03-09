#!/usr/bin/env python3
"""
Phase 7: Append new vacuum automations to automations.yaml
"""
import sys

NEW_AUTOMATIONS = """
- id: vacuum_carpet_mode_changed
  alias: 'Vacuum: Carpet mode changed'
  description: Set vacuum carpet mode when input_select changes
  triggers:
  - trigger: state
    entity_id: input_select.vacuum_carpet_mode
  conditions:
  - condition: template
    value_template: "{{ trigger.to_state.state not in ['unknown','unavailable'] }}"
  actions:
  - action: rest_command.vacuum_set_carpet_mode
    data:
      mode: "{{ states('input_select.vacuum_carpet_mode') }}"

- id: vacuum_auto_empty_interval_changed
  alias: 'Vacuum: Auto empty interval changed'
  description: Set vacuum auto empty interval when input_select changes
  triggers:
  - trigger: state
    entity_id: input_select.vacuum_auto_empty_interval
  conditions:
  - condition: template
    value_template: "{{ trigger.to_state.state not in ['unknown','unavailable'] }}"
  actions:
  - action: rest_command.vacuum_set_auto_empty_interval
    data:
      interval: "{{ states('input_select.vacuum_auto_empty_interval') }}"

- id: vacuum_drive_speed_changed
  alias: 'Vacuum: Drive speed changed'
  description: Set vacuum drive speed when input_number changes
  triggers:
  - trigger: state
    entity_id: input_number.vacuum_drive_speed
  conditions:
  - condition: template
    value_template: "{{ trigger.to_state.state not in ['unknown','unavailable'] }}"
  actions:
  - action: rest_command.vacuum_set_drive_speed
    data:
      speed: "{{ states('input_number.vacuum_drive_speed') | int }}"

- id: vacuum_new_controls_sync_on_startup
  alias: 'Vacuum: Sync new controls on startup'
  description: Sync carpet mode, auto empty interval, and drive speed from sensors on HA start
  triggers:
  - trigger: homeassistant
    event: start
  conditions: []
  actions:
  - delay:
      seconds: 30
  - action: input_select.select_option
    target:
      entity_id: input_select.vacuum_carpet_mode
    data:
      option: "{{ states('sensor.vacuum_carpet_mode') }}"
  - action: input_select.select_option
    target:
      entity_id: input_select.vacuum_auto_empty_interval
    data:
      option: "{{ states('sensor.vacuum_auto_empty_interval') }}"
  - action: input_number.set_value
    target:
      entity_id: input_number.vacuum_drive_speed
    data:
      value: "{{ states('sensor.vacuum_drive_speed') | int(50) }}"
"""

def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else '/config/automations.yaml'
    
    with open(config_path, 'a') as f:
        f.write(NEW_AUTOMATIONS)
    
    print(f"Appended automations to {config_path}")
    print("Added: carpet_mode_changed, auto_empty_interval_changed, drive_speed_changed, new_controls_sync_on_startup")

if __name__ == '__main__':
    main()
