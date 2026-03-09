#!/usr/bin/env python3
"""
Phase 7: Modify HA configuration.yaml to add new vacuum capability config.
Reads the file, inserts new entries into existing blocks, writes back.
"""
import sys
import re

def insert_after_last_block_entry(lines, block_marker, indent_marker, new_content):
    """Insert new_content after the last entry of a YAML block identified by block_marker.
    Looks for the block, finds the last entry at the given indent level, inserts after."""
    in_block = False
    last_entry_line = -1
    block_indent = None
    
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped == block_marker:
            in_block = True
            block_indent = len(line) - len(line.lstrip())
            continue
        if in_block:
            # Check if we've left the block (same or lower indent non-empty line that starts a new block)
            if stripped and not stripped.startswith('#') and not line.startswith(' '):
                break
            if stripped:
                last_entry_line = i
    
    if last_entry_line >= 0:
        lines.insert(last_entry_line + 1, new_content)
        return True
    return False

def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else '/config/configuration.yaml'
    
    with open(config_path, 'r') as f:
        content = f.read()
    
    # === REST COMMANDS ===
    # Insert new rest_commands before the "sensor:" block
    new_rest_commands = """
  # --- Drive Speed ---
  vacuum_set_drive_speed:
    url: "http://192.168.1.31:6971/drive/speed/{{ speed }}"
    method: GET

  # --- Carpet Sensor Mode ---
  vacuum_set_carpet_mode:
    url: "http://192.168.1.31:6971/carpet_mode/{{ mode }}"
    method: GET

  # --- Obstacle Images ---
  vacuum_obstacle_images_enable:
    url: "http://192.168.1.31:6971/obstacle_images/enable"
    method: GET

  vacuum_obstacle_images_disable:
    url: "http://192.168.1.31:6971/obstacle_images/disable"
    method: GET

  # --- Obstacle Avoidance ---
  vacuum_obstacle_avoidance_enable:
    url: "http://192.168.1.31:6971/obstacle_avoidance/enable"
    method: GET

  vacuum_obstacle_avoidance_disable:
    url: "http://192.168.1.31:6971/obstacle_avoidance/disable"
    method: GET

  # --- Child Lock ---
  vacuum_child_lock_enable:
    url: "http://192.168.1.31:6971/child_lock/enable"
    method: GET

  vacuum_child_lock_disable:
    url: "http://192.168.1.31:6971/child_lock/disable"
    method: GET

  # --- Auto Empty Interval ---
  vacuum_set_auto_empty_interval:
    url: "http://192.168.1.31:6971/auto_empty_interval/{{ interval }}"
    method: GET

  # --- DND ---
  vacuum_set_dnd:
    url: "http://192.168.1.31:6971/dnd"
    method: PUT
    content_type: "application/json"
    payload: >-
      {"enabled": {{ enabled }}, "start": {"hour": {{ start_hour }}, "minute": {{ start_minute }}}, "end": {"hour": {{ end_hour }}, "minute": {{ end_minute }}}}

  # --- Quirks ---
  vacuum_set_quirk:
    url: "http://192.168.1.31:6971/quirks"
    method: POST
    content_type: "application/json"
    payload: >-
      {"id": "{{ quirk_id }}", "value": "{{ value }}"}
"""
    
    # Insert before "sensor:" line
    content = content.replace(
        '\n  # Set video quality profile (low, high)\n  vacuum_set_video_quality:\n    url: "http://192.168.1.31:6971/video_quality/{{ profile }}"\n    method: GET\nsensor:',
        '\n  # Set video quality profile (low, high)\n  vacuum_set_video_quality:\n    url: "http://192.168.1.31:6971/video_quality/{{ profile }}"\n    method: GET\n' + new_rest_commands + 'sensor:'
    )
    
    # === SENSORS ===
    new_sensors = """
  - platform: rest
    name: Vacuum Total Statistics
    resource: "http://192.168.1.31:6971/statistics"
    value_template: >-
      {% set counts = value_json.total | selectattr('type','eq','count') | list %}
      {{ counts[0].value if counts else 0 }}
    json_attributes:
      - total
      - current
    scan_interval: 300

  - platform: rest
    name: Vacuum Consumables
    resource: "http://192.168.1.31:6971/consumables"
    value_template: "ok"
    json_attributes_path: "$[0]"
    json_attributes:
      - type
      - subType
      - remaining
    scan_interval: 3600

  - platform: rest
    name: Vacuum DND
    resource: "http://192.168.1.31:6971/dnd"
    value_template: "{{ value_json.enabled }}"
    json_attributes:
      - enabled
      - start
      - end
    scan_interval: 300

  - platform: rest
    name: Vacuum Carpet Mode
    resource: "http://192.168.1.31:6971/carpet_mode"
    value_template: "{{ value_json.mode }}"
    scan_interval: 60

  - platform: rest
    name: Vacuum Obstacle Images
    resource: "http://192.168.1.31:6971/obstacle_images"
    value_template: "{{ value_json.enabled }}"
    scan_interval: 300

  - platform: rest
    name: Vacuum Obstacle Avoidance
    resource: "http://192.168.1.31:6971/obstacle_avoidance"
    value_template: "{{ value_json.enabled }}"
    scan_interval: 300

  - platform: rest
    name: Vacuum Child Lock
    resource: "http://192.168.1.31:6971/child_lock"
    value_template: "{{ value_json.enabled }}"
    scan_interval: 300

  - platform: rest
    name: Vacuum Auto Empty Interval
    resource: "http://192.168.1.31:6971/auto_empty_interval"
    value_template: "{{ value_json.interval }}"
    scan_interval: 300

  - platform: rest
    name: Vacuum Drive Speed
    resource: "http://192.168.1.31:6971/drive/speed"
    value_template: "{{ value_json.speed }}"
    unit_of_measurement: "%"
    scan_interval: 60
"""
    
    # Insert after the last existing sensor (Vacuum Video Quality)
    content = content.replace(
        '    scan_interval: 60\ninput_number:',
        '    scan_interval: 60\n' + new_sensors + 'input_number:'
    )
    
    # === INPUT_NUMBER: Add drive speed ===
    new_input_number = """
  vacuum_drive_speed:
    name: Vacuum Drive Speed
    min: 10
    max: 100
    step: 10
    icon: mdi:speedometer
    unit_of_measurement: "%"
"""
    
    # Insert after vacuum_mic_volume input_number block
    content = content.replace(
        '    unit_of_measurement: "%"\n\ninput_text:',
        '    unit_of_measurement: "%"\n' + new_input_number + '\ninput_text:'
    )
    
    # === INPUT_SELECT: Add carpet mode and auto empty interval ===
    new_input_selects = """
  vacuum_carpet_mode:
    name: Vacuum Carpet Mode
    options:
      - "off"
      - avoid
      - lift
    icon: mdi:rug

  vacuum_auto_empty_interval:
    name: Vacuum Auto Empty Interval
    options:
      - normal
      - frequent
      - every_clean
    icon: mdi:delete-empty
"""
    
    # Insert after vacuum_video_quality input_select
    content = content.replace(
        '    icon: mdi:video\n# group:',
        '    icon: mdi:video\n' + new_input_selects + '# group:'
    )
    
    with open(config_path, 'w') as f:
        f.write(content)
    
    print(f"Updated {config_path}")
    print("Added: 11 rest_commands, 9 sensors, 1 input_number, 2 input_selects")

if __name__ == '__main__':
    main()
