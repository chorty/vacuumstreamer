# vacuumstreamer

Stream live video and two-way audio from Dreame/3iRobot vacuum cleaners running [Valetudo](https://valetudo.cloud/), with full Home Assistant integration including WebRTC camera, TTS (text-to-speech), and volume controls.

Uses the vacuum's built-in `video_monitor` binary with an `LD_PRELOAD` hook (`vacuumstreamer.so`) to intercept the Agora RTC video pipeline and redirect H.264 frames to a local TCP socket, which [go2rtc](https://github.com/AlexxIT/go2rtc) picks up for WebRTC/RTSP streaming.

Tested on: Dreame L10s Ultra (Allwinner MR813/sun50iw10, ARM64, Athena Linux).

## Features

- **Live video** — H.264 via WebRTC or RTSP, switchable quality profiles
- **Live audio** — Microphone capture from the vacuum
- **Two-way audio** — Talk through the vacuum speaker via WebRTC backchannel
- **Text-to-speech** — Google TTS HTTP endpoint, speak any text through the vacuum
- **Volume control** — Speaker and microphone volume via HTTP API
- **Vacuum controls** — Start/stop/pause/home, operation mode, fan speed, water usage
- **Manual driving** — Remote-control the vacuum with velocity/angle commands
- **Room cleaning** — Clean specific rooms by segment ID
- **Video quality switching** — Toggle between low (864×480/15fps/600kbps) and high (640×480/25fps/2Mbps) profiles
- **Home Assistant integration** — Full dashboard with camera, D-pad driving controls, mode/speed/quality selectors, TTS, and volume

## Architecture

```
video_monitor → vacuumstreamer.so (LD_PRELOAD) → TCP :6969 → go2rtc → WebRTC/RTSP
                                                               ↑
                                                    arecord (mic audio)
                                                               ↓ backchannel
                                                    play_pcm.sh → aplay → speaker

tcpsvd :6971 → tts_handler.sh → Google TTS → ffmpeg → aplay → speaker
                               → ogg123 → dmr_player → speaker
                               → amixer (volume control)
                               → Valetudo API proxy (controls, status, drive)
```

## Build

```bash
docker build -t vacuumstreamer .
./run.sh make
```

This cross-compiles `vacuumstreamer.so` for aarch64 using clang.

## Install

### 1. Core files

Copy the compiled library, `video_monitor` binary, and configuration to the vacuum:

```bash
VACUUM_IP=192.168.1.31

ssh root@${VACUUM_IP} "mkdir -p /data/vacuumstreamer"
scp -O vacuumstreamer.so root@${VACUUM_IP}:/data/vacuumstreamer/vacuumstreamer.so
scp -O dist/usr/bin/video_monitor root@${VACUUM_IP}:/data/vacuumstreamer/video_monitor
scp -Or dist/ava/conf/video_monitor/ root@${VACUUM_IP}:/data/vacuumstreamer/ava_conf_video_monitor
```

### 2. go2rtc

```bash
ssh root@${VACUUM_IP}
curl -L https://github.com/AlexxIT/go2rtc/releases/download/v1.9.9/go2rtc_linux_arm64 -o /data/vacuumstreamer/go2rtc
chmod +x /data/vacuumstreamer/go2rtc
```

### 3. ffmpeg (required for still frames and TTS)

```bash
ssh root@${VACUUM_IP}
curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz -o /tmp/ffmpeg.tar.xz
cd /tmp && tar xf ffmpeg.tar.xz
cp /tmp/ffmpeg-*-arm64-static/ffmpeg /data/vacuumstreamer/ffmpeg
chmod +x /data/vacuumstreamer/ffmpeg
rm -rf /tmp/ffmpeg*
```

### 4. Configuration files

Copy the runtime scripts and go2rtc config:

```bash
scp -O go2rtc.yaml root@${VACUUM_IP}:/data/vacuumstreamer/go2rtc.yaml
scp -O play_pcm.sh root@${VACUUM_IP}:/data/vacuumstreamer/play_pcm.sh
scp -O tts_handler.sh root@${VACUUM_IP}:/data/vacuumstreamer/tts_handler.sh
ssh root@${VACUUM_IP} "chmod +x /data/vacuumstreamer/play_pcm.sh /data/vacuumstreamer/tts_handler.sh"
```

**Important:** Edit `go2rtc.yaml` and update the `candidates` IP address to match your vacuum's IP.

### 5. Certificate workaround

```bash
ssh root@${VACUUM_IP}
cp -r /mnt/private /data/vacuumstreamer/mnt_private_copy
touch /data/vacuumstreamer/mnt_private_copy/certificate.bin
```

See [#1](https://github.com/tihmstar/vacuumstreamer/issues/1) for details.

### 6. Startup script

Copy the boot script to the vacuum:

```bash
scp -O _root_postboot.sh root@${VACUUM_IP}:/data/_root_postboot.sh
ssh root@${VACUUM_IP} "chmod +x /data/_root_postboot.sh"
```

Or append the vacuumstreamer block to your existing `_root_postboot.sh` — see the file for the full contents including WiFi power management, Valetudo startup, ALSA mixer configuration, and service launches.

## go2rtc Configuration

The `go2rtc.yaml` configures:

- **Video source** — TCP connection to `video_monitor` on port 6969
- **Audio source** — `arecord` capturing from the vacuum's microphone
- **Backchannel** — `play_pcm.sh` receives WebRTC audio and plays through the speaker via `aplay`
- **API** — Port 1984 (Web UI at `http://<VACUUM_IP>:1984`)
- **RTSP** — Port 8554 (`rtsp://<VACUUM_IP>:8554/vacuum`)
- **WebRTC** — Port 8555

## TTS & Audio HTTP API

The `tts_handler.sh` script runs via `tcpsvd` on port 6971 and provides:

| Endpoint | Method | Description |
|---|---|---|
| `/say` | POST | Text-to-speech via Google Translate TTS. Body: plain text |
| `/say?text=hello` | GET | TTS via query parameter |
| `/play` | POST | Play raw PCM audio (S16_LE, 16kHz, mono) |
| `/play_ogg` | POST | Play OGG file by path (body: filepath) |
| `/test` | GET | Play the vacuum's locate sound |
| `/volume` | GET | Get speaker volume as JSON: `{"volume":93,"raw":31}` |
| `/volume/N` | GET | Set speaker volume (0–100) |
| `/mic_volume` | GET | Get mic gain as JSON: `{"mic_volume":61,"raw":19}` |
| `/mic_volume/N` | GET | Set mic gain (0–100) |
| `/status` | GET | Get vacuum state (status, battery, mode, fan speed, water usage) |
| `/start` | GET | Start cleaning |
| `/stop` | GET | Stop cleaning |
| `/pause` | GET | Pause cleaning |
| `/home` | GET | Return to dock |
| `/mode` | GET | Get current operation mode |
| `/mode/MODE` | GET | Set mode: `vacuum`, `mop`, `vacuum_and_mop` |
| `/fan_speed` | GET | Get current fan speed |
| `/fan_speed/SPEED` | GET | Set fan speed: `low`, `medium`, `high`, `max` |
| `/water_usage` | GET | Get current water usage level |
| `/water_usage/LEVEL` | GET | Set water usage: `min`, `low`, `medium`, `high`, `max` |
| `/drive/enable` | GET | Enable manual driving mode |
| `/drive/disable` | GET | Disable manual driving mode |
| `/drive/move` | POST | Move vacuum. Body: `{"velocity": -1..1, "angle": -180..180}` |
| `/segments` | GET | List map segments (rooms) |
| `/segments/clean` | POST | Clean rooms. Body: `{"segment_ids": ["1","2"], "iterations": 1}` |
| `/video_quality` | GET | Get current video profile: `{"profile":"low","width":864,"height":480,"framerate":15,"bitrate":600000}` |
| `/video_quality/PROFILE` | GET | Set video profile: `low` (864×480/15fps/600kbps) or `high` (640×480/25fps/2Mbps). Restarts video_monitor |

### Examples

```bash
# Text-to-speech
curl -X POST -d "Hello from the vacuum" http://192.168.1.31:6971/say

# Set speaker volume to 75%
curl http://192.168.1.31:6971/volume/75

# Get current volume
curl http://192.168.1.31:6971/volume

# Play locate sound
curl http://192.168.1.31:6971/test

# Start cleaning
curl http://192.168.1.31:6971/start

# Set to mop mode
curl http://192.168.1.31:6971/mode/mop

# Manual drive: move forward
curl http://192.168.1.31:6971/drive/enable
curl -X POST -d '{"velocity": 0.3, "angle": 0}' http://192.168.1.31:6971/drive/move
curl http://192.168.1.31:6971/drive/disable

# Clean specific rooms
curl -X POST -d '{"segment_ids": ["3","4"], "iterations": 1}' http://192.168.1.31:6971/segments/clean

# Get current video quality
curl http://192.168.1.31:6971/video_quality

# Switch to high quality
curl http://192.168.1.31:6971/video_quality/high

# Switch back to low quality
curl http://192.168.1.31:6971/video_quality/low
```

## Home Assistant Integration

### Prerequisites

- [WebRTC Camera](https://github.com/AlexxIT/WebRTC) custom integration (install via HACS)
- [Generic Camera](https://www.home-assistant.io/integrations/generic/) integration (for still image)

### Generic Camera setup

Add a Generic Camera integration in HA with:
- **Still Image URL:** `http://<VACUUM_IP>:1984/api/frame.jpeg?src=vacuum`
- **Stream Source:** `rtsp://<VACUUM_IP>:8554/vacuum`

### configuration.yaml

Add the following to your Home Assistant `configuration.yaml` (replace `192.168.1.31` with your vacuum IP):

```yaml
rest_command:
  # --- Audio Commands ---
  vacuum_say:
    url: "http://192.168.1.31:6971/say"
    method: POST
    content_type: "text/plain"
    payload: "{{ message }}"
    timeout: 30

  vacuum_set_volume:
    url: "http://192.168.1.31:6971/volume/{{ volume }}"
    method: GET

  vacuum_set_mic_volume:
    url: "http://192.168.1.31:6971/mic_volume/{{ volume }}"
    method: GET

  vacuum_test_sound:
    url: "http://192.168.1.31:6971/test"
    method: GET

  vacuum_play_ogg:
    url: "http://192.168.1.31:6971/play_ogg"
    method: POST
    content_type: "text/plain"
    payload: "{{ ogg_path }}"

  # --- Vacuum Control Commands ---
  vacuum_start:
    url: "http://192.168.1.31:6971/start"
    method: GET

  vacuum_stop:
    url: "http://192.168.1.31:6971/stop"
    method: GET

  vacuum_pause:
    url: "http://192.168.1.31:6971/pause"
    method: GET

  vacuum_home:
    url: "http://192.168.1.31:6971/home"
    method: GET

  vacuum_set_mode:
    url: "http://192.168.1.31:6971/mode/{{ mode }}"
    method: GET

  vacuum_set_fan_speed:
    url: "http://192.168.1.31:6971/fan_speed/{{ speed }}"
    method: GET

  vacuum_set_water_usage:
    url: "http://192.168.1.31:6971/water_usage/{{ level }}"
    method: GET

  # --- Manual Drive Commands ---
  vacuum_drive_enable:
    url: "http://192.168.1.31:6971/drive/enable"
    method: GET

  vacuum_drive_disable:
    url: "http://192.168.1.31:6971/drive/disable"
    method: GET

  vacuum_drive_move:
    url: "http://192.168.1.31:6971/drive/move"
    method: POST
    content_type: "application/json"
    payload: >-
      {"velocity": {{ velocity }}, "angle": {{ angle }}}

  # --- Video Quality ---
  vacuum_set_video_quality:
    url: "http://192.168.1.31:6971/video_quality/{{ profile }}"
    method: GET

  # --- Room Cleaning ---
  vacuum_clean_segments:
    url: "http://192.168.1.31:6971/segments/clean"
    method: POST
    content_type: "application/json"
    payload: >-
      {"segment_ids": {{ segment_ids }}, "iterations": {{ iterations | default(1) }}}

# Sensors
sensor:
  - platform: rest
    name: Vacuum Speaker Volume
    resource: "http://192.168.1.31:6971/volume"
    value_template: "{{ value_json.volume }}"
    unit_of_measurement: "%"
    scan_interval: 60

  - platform: rest
    name: Vacuum Mic Volume
    resource: "http://192.168.1.31:6971/mic_volume"
    value_template: "{{ value_json.mic_volume }}"
    unit_of_measurement: "%"
    scan_interval: 60

  - platform: rest
    name: Vacuum Status
    resource: "http://192.168.1.31:6971/status"
    value_template: >-
      {% for attr in value_json if attr.__class == "StatusStateAttribute" %}{{ attr.value }}{% endfor %}
    scan_interval: 30

  - platform: rest
    name: Vacuum Battery
    resource: "http://192.168.1.31:6971/status"
    device_class: battery
    unit_of_measurement: "%"
    value_template: >-
      {% for attr in value_json if attr.__class == "BatteryStateAttribute" %}{{ attr.level }}{% endfor %}
    scan_interval: 60

  - platform: rest
    name: Vacuum Mode
    resource: "http://192.168.1.31:6971/mode"
    value_template: "{{ value_json.mode }}"
    scan_interval: 30

  - platform: rest
    name: Vacuum Fan Speed
    resource: "http://192.168.1.31:6971/fan_speed"
    value_template: "{{ value_json.fan_speed }}"
    scan_interval: 30

  - platform: rest
    name: Vacuum Water Usage
    resource: "http://192.168.1.31:6971/water_usage"
    value_template: "{{ value_json.water_usage }}"
    scan_interval: 30

  - platform: rest
    name: Vacuum Video Quality
    resource: "http://192.168.1.31:6971/video_quality"
    value_template: "{{ value_json.profile }}"
    json_attributes:
      - width
      - height
      - framerate
      - bitrate
    scan_interval: 60

# Input controls
input_number:
  vacuum_speaker_volume:
    name: Vacuum Speaker Volume
    min: 0
    max: 100
    step: 5
    icon: mdi:volume-high
    unit_of_measurement: "%"

  vacuum_mic_volume:
    name: Vacuum Mic Volume
    min: 0
    max: 100
    step: 5
    icon: mdi:microphone
    unit_of_measurement: "%"

input_text:
  vacuum_tts_message:
    name: Vacuum TTS Message
    max: 200
    icon: mdi:message-text

input_select:
  vacuum_mode:
    name: Vacuum Mode
    options:
      - vacuum
      - mop
      - vacuum_and_mop
    icon: mdi:robot-vacuum

  vacuum_fan_speed:
    name: Vacuum Fan Speed
    options:
      - low
      - medium
      - high
      - max
    icon: mdi:fan

  vacuum_water_usage:
    name: Vacuum Water Usage
    options:
      - min
      - low
      - medium
      - high
      - max
    icon: mdi:water

  vacuum_video_quality:
    name: Vacuum Video Quality
    options:
      - low
      - high
    icon: mdi:video

# Scripts
script:
  vacuum_speak:
    alias: Vacuum Speak
    sequence:
      - action: rest_command.vacuum_say
        data:
          message: "{{ message }}"

  vacuum_speak_from_input:
    alias: Vacuum Speak From Input
    sequence:
      - action: rest_command.vacuum_say
        data:
          message: "{{ states('input_text.vacuum_tts_message') }}"
```

### Automations

Create the following automations (via the HA UI or `automations.yaml`):

**Sync volume sliders → vacuum:**

```yaml
- alias: Vacuum Speaker Volume Changed
  trigger:
    - platform: state
      entity_id: input_number.vacuum_speaker_volume
  condition:
    - condition: template
      value_template: "{{ trigger.from_state.state not in ['unknown', 'unavailable'] }}"
  action:
    - action: rest_command.vacuum_set_volume
      data:
        volume: "{{ states('input_number.vacuum_speaker_volume') | int }}"

- alias: Vacuum Mic Volume Changed
  trigger:
    - platform: state
      entity_id: input_number.vacuum_mic_volume
  condition:
    - condition: template
      value_template: "{{ trigger.from_state.state not in ['unknown', 'unavailable'] }}"
  action:
    - action: rest_command.vacuum_set_mic_volume
      data:
        volume: "{{ states('input_number.vacuum_mic_volume') | int }}"
```

**Sync mode/speed/water selectors → vacuum:**

```yaml
- alias: Vacuum Mode Changed
  trigger:
    - platform: state
      entity_id: input_select.vacuum_mode
  condition:
    - condition: template
      value_template: "{{ trigger.from_state.state not in ['unknown', 'unavailable'] and trigger.from_state.state != trigger.to_state.state }}"
  action:
    - action: rest_command.vacuum_set_mode
      data:
        mode: "{{ states('input_select.vacuum_mode') }}"

- alias: Vacuum Fan Speed Changed
  trigger:
    - platform: state
      entity_id: input_select.vacuum_fan_speed
  condition:
    - condition: template
      value_template: "{{ trigger.from_state.state not in ['unknown', 'unavailable'] and trigger.from_state.state != trigger.to_state.state }}"
  action:
    - action: rest_command.vacuum_set_fan_speed
      data:
        speed: "{{ states('input_select.vacuum_fan_speed') }}"

- alias: Vacuum Water Usage Changed
  trigger:
    - platform: state
      entity_id: input_select.vacuum_water_usage
  condition:
    - condition: template
      value_template: "{{ trigger.from_state.state not in ['unknown', 'unavailable'] and trigger.from_state.state != trigger.to_state.state }}"
  action:
    - action: rest_command.vacuum_set_water_usage
      data:
        level: "{{ states('input_select.vacuum_water_usage') }}"

- alias: Vacuum Video Quality Changed
  trigger:
    - platform: state
      entity_id: input_select.vacuum_video_quality
  condition:
    - condition: template
      value_template: "{{ trigger.from_state.state not in ['unknown', 'unavailable'] and trigger.from_state.state != trigger.to_state.state }}"
  action:
    - action: rest_command.vacuum_set_video_quality
      data:
        profile: "{{ states('input_select.vacuum_video_quality') }}"
```

**Sync vacuum → sliders/selectors on startup:**

```yaml
- alias: Vacuum Controls Sync on Startup
  trigger:
    - platform: homeassistant
      event: start
  action:
    - delay:
        seconds: 30
    - action: input_number.set_value
      target:
        entity_id: input_number.vacuum_speaker_volume
      data:
        value: "{{ states('sensor.vacuum_speaker_volume') | int(50) }}"
    - action: input_number.set_value
      target:
        entity_id: input_number.vacuum_mic_volume
      data:
        value: "{{ states('sensor.vacuum_mic_volume') | int(50) }}"
    - action: input_select.select_option
      target:
        entity_id: input_select.vacuum_mode
      data:
        option: "{{ states('sensor.vacuum_mode') }}"
    - action: input_select.select_option
      target:
        entity_id: input_select.vacuum_fan_speed
      data:
        option: "{{ states('sensor.vacuum_fan_speed') }}"
    - action: input_select.select_option
      target:
        entity_id: input_select.vacuum_water_usage
      data:
        option: "{{ states('sensor.vacuum_water_usage') }}"
    - action: input_select.select_option
      target:
        entity_id: input_select.vacuum_video_quality
      data:
        option: "{{ states('sensor.vacuum_video_quality') }}"
```

### Dashboard Card

Add a vertical-stack card to your Lovelace dashboard for a full vacuum control panel:

```yaml
type: vertical-stack
cards:
  # --- Live Camera Feed ---
  - type: custom:webrtc-camera
    url: vacuum
    mode: webrtc
    media: video,audio,microphone
    server: http://192.168.1.31:1984

  # --- Status Bar ---
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-entity-card
        entity: sensor.vacuum_status
        name: Status
        icon: mdi:robot-vacuum
      - type: custom:mushroom-entity-card
        entity: sensor.vacuum_battery
        name: Battery
        icon: mdi:battery
      - type: custom:mushroom-entity-card
        entity: sensor.vacuum_mode
        name: Mode
        icon: mdi:auto-fix

  # --- Vacuum Actions ---
  - type: horizontal-stack
    cards:
      - type: button
        name: Start
        icon: mdi:play
        tap_action:
          action: call-service
          service: rest_command.vacuum_start
      - type: button
        name: Pause
        icon: mdi:pause
        tap_action:
          action: call-service
          service: rest_command.vacuum_pause
      - type: button
        name: Stop
        icon: mdi:stop
        tap_action:
          action: call-service
          service: rest_command.vacuum_stop
      - type: button
        name: Home
        icon: mdi:home
        tap_action:
          action: call-service
          service: rest_command.vacuum_home

  # --- Manual Drive D-Pad ---
  - type: vertical-stack
    cards:
      - type: horizontal-stack
        cards:
          - type: button
            name: ""
            icon: ""
            tap_action:
              action: none
          - type: button
            name: Forward
            icon: mdi:arrow-up-bold
            tap_action:
              action: call-service
              service: script.vacuum_drive_forward
          - type: button
            name: ""
            icon: ""
            tap_action:
              action: none
      - type: horizontal-stack
        cards:
          - type: button
            name: Left
            icon: mdi:arrow-left-bold
            tap_action:
              action: call-service
              service: script.vacuum_drive_left
          - type: button
            name: Enable
            icon: mdi:gamepad-variant
            tap_action:
              action: call-service
              service: rest_command.vacuum_drive_enable
          - type: button
            name: Right
            icon: mdi:arrow-right-bold
            tap_action:
              action: call-service
              service: script.vacuum_drive_right
      - type: horizontal-stack
        cards:
          - type: button
            name: ""
            icon: ""
            tap_action:
              action: none
          - type: button
            name: Back
            icon: mdi:arrow-down-bold
            tap_action:
              action: call-service
              service: script.vacuum_drive_backward
          - type: button
            name: ""
            icon: ""
            tap_action:
              action: none

  # --- Mode & Speed Selectors ---
  - type: entities
    title: Vacuum Settings
    entities:
      - entity: input_select.vacuum_mode
        name: Operation Mode
      - entity: input_select.vacuum_fan_speed
        name: Fan Speed
      - entity: input_select.vacuum_water_usage
        name: Water Usage
      - entity: input_select.vacuum_video_quality
        name: Video Quality

  # --- Volume Controls ---
  - type: entities
    title: Audio Controls
    entities:
      - entity: input_number.vacuum_speaker_volume
        name: Speaker Volume
      - entity: input_number.vacuum_mic_volume
        name: Mic Volume

  # --- TTS ---
  - type: horizontal-stack
    cards:
      - type: entities
        entities:
          - entity: input_text.vacuum_tts_message
            name: Say something...
      - type: button
        name: Speak
        icon: mdi:bullhorn
        tap_action:
          action: call-service
          service: script.vacuum_speak_from_input

  # --- Quick Actions ---
  - type: horizontal-stack
    cards:
      - type: button
        name: Locate
        icon: mdi:map-marker
        tap_action:
          action: call-service
          service: rest_command.vacuum_test_sound
      - type: button
        name: Say Hello
        icon: mdi:hand-wave
        tap_action:
          action: call-service
          service: rest_command.vacuum_say
          data:
            message: Hello from Home Assistant!
```

The D-pad drive scripts should be added to your HA scripts:

```yaml
script:
  vacuum_drive_forward:
    alias: Vacuum Drive Forward
    sequence:
      - action: rest_command.vacuum_drive_move
        data:
          velocity: "0.5"
          angle: "0"

  vacuum_drive_backward:
    alias: Vacuum Drive Backward
    sequence:
      - action: rest_command.vacuum_drive_move
        data:
          velocity: "-0.5"
          angle: "0"

  vacuum_drive_left:
    alias: Vacuum Drive Left
    sequence:
      - action: rest_command.vacuum_drive_move
        data:
          velocity: "0"
          angle: "90"

  vacuum_drive_right:
    alias: Vacuum Drive Right
    sequence:
      - action: rest_command.vacuum_drive_move
        data:
          velocity: "0"
          angle: "-90"
```

The card provides:
- **Live video** with WebRTC (low latency)
- **Live audio** from the vacuum's microphone
- **Two-way audio** — click the microphone button to talk through the vacuum speaker
- **Status bar** showing current status, battery level, and operation mode
- **Action buttons** — Start, Pause, Stop, Home
- **D-pad controls** — manual drive with Forward/Back/Left/Right and Enable button
- **Mode selectors** — operation mode, fan speed, water usage dropdowns
- **Volume sliders** for speaker and microphone
- **TTS text box** with a Speak button
- **Quick actions** — Locate and Say Hello buttons

## File Reference

| File | Description |
|---|---|
| `vacuumstreamer.c` | LD_PRELOAD hook — intercepts Agora RTC calls, redirects H.264 video to TCP :6969 |
| `vacuumstreamer.so` | Compiled shared library (aarch64) |
| `go2rtc.yaml` | go2rtc configuration — streams, RTSP, WebRTC, backchannel |
| `play_pcm.sh` | WebRTC backchannel handler — pipes PCM audio to `aplay` |
| `tts_handler.sh` | HTTP server handler for TTS, audio playback, volume control, video quality switching, and Valetudo API proxy (vacuum controls, manual drive, mode/speed/water, room cleaning) |
| `_root_postboot.sh` | Boot script — starts Valetudo, ALSA mixer setup, video_monitor, go2rtc, TTS server |
| `Dockerfile` | Build environment for cross-compiling vacuumstreamer.so |
| `run.sh` | Docker wrapper for running make |

## Credits

- [@tihmstar](https://github.com/tihmstar) — vacuumstreamer
- [@Uberi](https://github.com/Uberi) — research and documentation: https://anthony-zhang.me/blog/offline-robot-vacuum/
- [@dgiese](https://github.com/dgiese) — vacuum security research
- [go2rtc](https://github.com/AlexxIT/go2rtc) — WebRTC/RTSP streaming
- [Valetudo](https://valetudo.cloud/) — open-source vacuum control
