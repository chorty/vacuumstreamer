# vacuumstreamer

Stream live video and two-way audio from Dreame/3iRobot vacuum cleaners running [Valetudo](https://valetudo.cloud/), with full Home Assistant integration including WebRTC camera, TTS (text-to-speech), and volume controls.

Uses the vacuum's built-in `video_monitor` binary with an `LD_PRELOAD` hook (`vacuumstreamer.so`) to intercept the Agora RTC video pipeline and redirect H.264 frames to a local TCP socket, which [go2rtc](https://github.com/AlexxIT/go2rtc) picks up for WebRTC/RTSP streaming.

Tested on: Dreame L10s Ultra (Allwinner MR813/sun50iw10, ARM64, Athena Linux).

## Features

- **Live video** — H.264, 864×480, ~15fps via WebRTC or RTSP
- **Live audio** — Microphone capture from the vacuum
- **Two-way audio** — Talk through the vacuum speaker via WebRTC backchannel
- **Text-to-speech** — Google TTS HTTP endpoint, speak any text through the vacuum
- **Volume control** — Speaker and microphone volume via HTTP API
- **Home Assistant integration** — WebRTC camera card with volume sliders, TTS input, and action buttons

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

Add the following to your Home Assistant `configuration.yaml`:

```yaml
# REST commands for vacuum audio control
rest_command:
  vacuum_say:
    url: "http://192.168.1.31:6971/say"
    method: POST
    content_type: "text/plain"
    payload: "{{ message }}"
    timeout: 30

  vacuum_set_volume:
    url: "http://192.168.1.31:6971/volume/{{ volume }}"
    method: GET
    timeout: 10

  vacuum_set_mic_volume:
    url: "http://192.168.1.31:6971/mic_volume/{{ volume }}"
    method: GET
    timeout: 10

  vacuum_test_sound:
    url: "http://192.168.1.31:6971/test"
    method: GET
    timeout: 10

  vacuum_play_ogg:
    url: "http://192.168.1.31:6971/play_ogg"
    method: POST
    content_type: "text/plain"
    payload: "{{ filepath }}"
    timeout: 10

# Sensors to read current volume levels
sensor:
  - platform: rest
    name: Vacuum Speaker Volume
    resource: "http://192.168.1.31:6971/volume"
    value_template: "{{ value_json.volume }}"
    scan_interval: 30

  - platform: rest
    name: Vacuum Mic Volume
    resource: "http://192.168.1.31:6971/mic_volume"
    value_template: "{{ value_json.mic_volume }}"
    scan_interval: 30

# Input controls for the dashboard
input_number:
  vacuum_speaker_volume:
    name: Vacuum Speaker Volume
    min: 0
    max: 100
    step: 1
    icon: mdi:volume-high

  vacuum_mic_volume:
    name: Vacuum Mic Volume
    min: 0
    max: 100
    step: 1
    icon: mdi:microphone

input_text:
  vacuum_tts_message:
    name: Vacuum TTS Message
    max: 255
    icon: mdi:message-text

# Scripts for TTS
script:
  vacuum_speak:
    alias: Vacuum Speak
    sequence:
      - service: rest_command.vacuum_say
        data:
          message: "{{ message }}"

  vacuum_speak_from_input:
    alias: Vacuum Speak From Input
    sequence:
      - service: rest_command.vacuum_say
        data:
          message: "{{ states('input_text.vacuum_tts_message') }}"
```

### Automations

Create the following automations (via the HA UI or `automations.yaml`):

**Sync slider → vacuum** (when the user moves a slider, send the value to the vacuum):

```yaml
- alias: Vacuum Speaker Volume Changed
  trigger:
    - platform: state
      entity_id: input_number.vacuum_speaker_volume
  action:
    - service: rest_command.vacuum_set_volume
      data:
        volume: "{{ states('input_number.vacuum_speaker_volume') | int }}"

- alias: Vacuum Mic Volume Changed
  trigger:
    - platform: state
      entity_id: input_number.vacuum_mic_volume
  action:
    - service: rest_command.vacuum_set_mic_volume
      data:
        volume: "{{ states('input_number.vacuum_mic_volume') | int }}"
```

**Sync sensor → slider** (on HA startup or when the sensor updates, sync the slider to match):

```yaml
- alias: Vacuum Volume Sync on Startup
  trigger:
    - platform: homeassistant
      event: start
    - platform: state
      entity_id: sensor.vacuum_speaker_volume
    - platform: state
      entity_id: sensor.vacuum_mic_volume
  action:
    - service: input_number.set_value
      target:
        entity_id: input_number.vacuum_speaker_volume
      data:
        value: "{{ states('sensor.vacuum_speaker_volume') | int(50) }}"
    - service: input_number.set_value
      target:
        entity_id: input_number.vacuum_mic_volume
      data:
        value: "{{ states('sensor.vacuum_mic_volume') | int(50) }}"
```

### Dashboard Card

Add a vertical-stack card to your Lovelace dashboard:

```yaml
type: vertical-stack
cards:
  - type: custom:webrtc-camera
    url: vacuum
    mode: webrtc
    media: video,audio,microphone
    server: http://192.168.1.31:1984
  - type: entities
    title: Vacuum Audio
    entities:
      - entity: input_number.vacuum_speaker_volume
        name: Speaker Volume
      - entity: input_number.vacuum_mic_volume
        name: Mic Volume
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

The card provides:
- **Live video** with WebRTC (low latency)
- **Live audio** from the vacuum's microphone
- **Two-way audio** — click the microphone button to talk through the vacuum speaker
- **Volume sliders** for speaker and microphone
- **TTS text box** with a Speak button
- **Locate** button to play the vacuum's locate sound
- **Say Hello** button for a quick TTS test

## File Reference

| File | Description |
|---|---|
| `vacuumstreamer.c` | LD_PRELOAD hook — intercepts Agora RTC calls, redirects H.264 video to TCP :6969 |
| `vacuumstreamer.so` | Compiled shared library (aarch64) |
| `go2rtc.yaml` | go2rtc configuration — streams, RTSP, WebRTC, backchannel |
| `play_pcm.sh` | WebRTC backchannel handler — pipes PCM audio to `aplay` |
| `tts_handler.sh` | HTTP server handler for TTS, audio playback, and volume control |
| `_root_postboot.sh` | Boot script — starts Valetudo, ALSA mixer setup, video_monitor, go2rtc, TTS server |
| `Dockerfile` | Build environment for cross-compiling vacuumstreamer.so |
| `run.sh` | Docker wrapper for running make |

## Credits

- [@tihmstar](https://github.com/tihmstar) — vacuumstreamer
- [@Uberi](https://github.com/Uberi) — research and documentation: https://anthony-zhang.me/blog/offline-robot-vacuum/
- [@dgiese](https://github.com/dgiese) — vacuum security research
- [go2rtc](https://github.com/AlexxIT/go2rtc) — WebRTC/RTSP streaming
- [Valetudo](https://valetudo.cloud/) — open-source vacuum control
