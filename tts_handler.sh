#!/bin/sh
# TTS/Audio HTTP handler for vacuum speaker
# Endpoints:
#   POST /say        - Text-to-speech: POST text body, vacuum speaks it (Google TTS)
#   POST /play       - Play raw PCM (S16_LE, 16kHz, mono) from request body
#   POST /play_raw   - Play raw PCM (S16_LE, 16kHz, mono) from request body (alias)
#   POST /play_ogg   - Play OGG file by path (body: filepath)
#   GET  /test       - Play locate sound
#   GET  /volume/N   - Set speaker volume (0-100)
#   GET  /volume     - Get current speaker volume
#   GET  /mic_volume/N - Set microphone gain (0-100)
#   GET  /mic_volume   - Get current microphone gain
#
# Usage: tcpsvd -vE 0.0.0.0 6971 /data/vacuumstreamer/tts_handler.sh

FFMPEG="/data/vacuumstreamer/ffmpeg"

read -r REQUEST_LINE
METHOD=$(echo "$REQUEST_LINE" | cut -d" " -f1)
URI=$(echo "$REQUEST_LINE" | cut -d" " -f2)

# Read headers
CONTENT_LENGTH=0
while read -r HEADER; do
    HEADER=$(echo "$HEADER" | tr -d "\r")
    [ -z "$HEADER" ] && break
    case "$HEADER" in
        Content-Length:*|content-length:*)
            CONTENT_LENGTH=$(echo "$HEADER" | cut -d: -f2 | tr -d " ")
            ;;
    esac
done

send_response() {
    CODE="$1"
    BODY="$2"
    LEN=$(echo -n "$BODY" | wc -c | tr -d ' ')
    printf 'HTTP/1.0 %s\r\n' "$CODE"
    printf 'Content-Type: text/plain\r\n'
    printf 'Content-Length: %s\r\n' "$LEN"
    printf 'Access-Control-Allow-Origin: *\r\n'
    printf 'Connection: close\r\n'
    printf '\r\n'
    printf '%s' "$BODY"
}

send_json_response() {
    CODE="$1"
    BODY="$2"
    LEN=$(echo -n "$BODY" | wc -c | tr -d ' ')
    printf 'HTTP/1.0 %s\r\n' "$CODE"
    printf 'Content-Type: application/json\r\n'
    printf 'Content-Length: %s\r\n' "$LEN"
    printf 'Access-Control-Allow-Origin: *\r\n'
    printf 'Connection: close\r\n'
    printf '\r\n'
    printf '%s' "$BODY"
}

# URL-decode a string (e.g. %20 -> space, + -> space)
urldecode() {
    echo "$1" | sed 's/+/ /g' | sed 's/%\([0-9A-Fa-f][0-9A-Fa-f]\)/\\x\1/g' | xargs -0 printf "%b" 2>/dev/null
}

# Extract base path (before query string)
BASE_PATH=$(echo "$URI" | cut -d'?' -f1)
QUERY_STRING=$(echo "$URI" | grep -o '?.*' | cut -c2-)

case "$BASE_PATH" in
    /say)
        # Accept text via POST body or GET ?text=...
        if [ "$METHOD" = "POST" ] && [ "$CONTENT_LENGTH" -gt 0 ]; then
            TEXT=$(dd bs=1 count=$CONTENT_LENGTH 2>/dev/null | tr -d "\r\n")
        elif [ -n "$QUERY_STRING" ]; then
            TEXT=$(echo "$QUERY_STRING" | sed 's/^text=//;s/&.*//')
            TEXT=$(urldecode "$TEXT")
        else
            send_response "400 Bad Request" "POST text body or GET /say?text=hello"
            exit 0
        fi

        if [ -z "$TEXT" ]; then
            send_response "400 Bad Request" "empty text"
            exit 0
        fi

        # URL-encode text for Google TTS
        ENCODED=$(echo -n "$TEXT" | sed 's/ /+/g;s/[^a-zA-Z0-9_.+~-]/%&/g' | sed 's/%\(.\)/\1/g' | cat -v | sed 's/ /+/g')
        # Simple URL encoding: replace spaces with +
        ENCODED=$(echo -n "$TEXT" | sed 's/ /+/g')
        TMP_MP3="/tmp/tts_say_$$.mp3"

        # Download TTS audio from Google
        curl -s -A "Mozilla/5.0" \
            -o "$TMP_MP3" \
            "https://translate.google.com/translate_tts?ie=UTF-8&q=${ENCODED}&tl=en&client=tw-ob" 2>/dev/null

        if [ -s "$TMP_MP3" ]; then
            # Convert MP3 to PCM and play
            "$FFMPEG" -i "$TMP_MP3" -f s16le -ar 16000 -ac 1 -acodec pcm_s16le - 2>/dev/null | \
                aplay -D default -f S16_LE -r 16000 -c 1 -t raw - > /dev/null 2>&1
            rm -f "$TMP_MP3"
            send_response "200 OK" "said: $TEXT"
        else
            rm -f "$TMP_MP3"
            send_response "500 Internal Server Error" "TTS failed"
        fi
        ;;
    /play)
        if [ "$METHOD" = "POST" ] && [ "$CONTENT_LENGTH" -gt 0 ]; then
            TMP_RAW=/tmp/tts_play_$$.raw
            TMP_OGG=/tmp/tts_play_$$.ogg
            dd bs=1 count=$CONTENT_LENGTH of=$TMP_RAW 2>/dev/null
            # Convert raw PCM to OGG, then play via dmr_player
            oggenc --raw --raw-bits=16 --raw-chan=1 --raw-rate=16000 \
                   --raw-endianness=0 -Q -o "$TMP_OGG" "$TMP_RAW" > /dev/null 2>&1
            ogg123 "$TMP_OGG" > /dev/null 2>&1
            rm -f "$TMP_RAW" "$TMP_OGG"
            send_response "200 OK" "played"
        else
            send_response "400 Bad Request" "POST with raw PCM body required"
        fi
        ;;
    /play_raw)
        if [ "$METHOD" = "POST" ] && [ "$CONTENT_LENGTH" -gt 0 ]; then
            TMP_RAW=/tmp/tts_raw_$$.raw
            TMP_OGG=/tmp/tts_raw_$$.ogg
            dd bs=1 count=$CONTENT_LENGTH of=$TMP_RAW 2>/dev/null
            oggenc --raw --raw-bits=16 --raw-chan=1 --raw-rate=16000 \
                   --raw-endianness=0 -Q -o "$TMP_OGG" "$TMP_RAW" > /dev/null 2>&1
            ogg123 "$TMP_OGG" > /dev/null 2>&1
            rm -f "$TMP_RAW" "$TMP_OGG"
            send_response "200 OK" "played"
        else
            send_response "400 Bad Request" "POST with raw PCM body required"
        fi
        ;;
    /play_ogg)
        if [ "$METHOD" = "POST" ] && [ "$CONTENT_LENGTH" -gt 0 ]; then
            OGG_PATH=$(dd bs=1 count=$CONTENT_LENGTH 2>/dev/null | tr -d "\r\n")
            if [ -f "$OGG_PATH" ]; then
                ogg123 "$OGG_PATH" > /dev/null 2>&1
                send_response "200 OK" "played $OGG_PATH"
            else
                send_response "404 Not Found" "file not found: $OGG_PATH"
            fi
        else
            send_response "400 Bad Request" "POST with ogg filepath in body"
        fi
        ;;
    /test)
        ogg123 /audio/EN/45.ogg > /dev/null 2>&1
        send_response "200 OK" "test sound played"
        ;;
    /volume)
        # GET /volume - return current LINEOUT volume as percentage
        # LINEOUT range: 0-31, mapped from 0-100 via mediad_set_real_volume.sh
        # MR813: real = value * 0.16 + 16, so value = (real - 16) / 0.16
        RAW=$(amixer cget numid=7 2>/dev/null | grep ': values=' | sed 's/.*values=//')
        # Convert LINEOUT raw (0-31) back to percentage (0-100)
        if [ "$RAW" -le 16 ] 2>/dev/null; then
            PCT=0
        else
            PCT=$(( (RAW - 16) * 100 / 16 ))
            [ "$PCT" -gt 100 ] && PCT=100
        fi
        send_json_response "200 OK" "{\"volume\":$PCT,\"raw\":$RAW}"
        ;;
    /volume/*)
        VOL=$(echo "$BASE_PATH" | sed 's|/volume/||')
        /ava/script/mediad_set_real_volume.sh set "$VOL" > /dev/null 2>&1
        send_response "200 OK" "volume set to $VOL"
        ;;
    /mic_volume)
        # GET /mic_volume - return current mic gain as percentage
        # MIC gain range: 0-31
        RAW=$(amixer cget numid=5 2>/dev/null | grep ': values=' | sed 's/.*values=//')
        PCT=$(( RAW * 100 / 31 ))
        send_json_response "200 OK" "{\"mic_volume\":$PCT,\"raw\":$RAW}"
        ;;
    /mic_volume/*)
        # Set mic gain: 0-100 mapped to 0-31
        MIC_PCT=$(echo "$BASE_PATH" | sed 's|/mic_volume/||')
        MIC_RAW=$(( MIC_PCT * 31 / 100 ))
        [ "$MIC_RAW" -gt 31 ] && MIC_RAW=31
        [ "$MIC_RAW" -lt 0 ] && MIC_RAW=0
        amixer cset numid=5 "$MIC_RAW" > /dev/null 2>&1
        amixer cset numid=6 "$MIC_RAW" > /dev/null 2>&1
        send_response "200 OK" "mic volume set to $MIC_PCT (raw: $MIC_RAW)"
        ;;
    *)
        send_response "404 Not Found" "endpoints: POST /say, POST /play, POST /play_ogg, GET /test, GET /volume[/N], GET /mic_volume[/N]"
        ;;
esac
