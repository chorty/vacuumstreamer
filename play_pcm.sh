#!/bin/sh
# play_pcm.sh - Backchannel handler for go2rtc
# Input: raw PCM S16_LE 16000Hz mono on stdin
# Plays directly via aplay
exec aplay -D default -f S16_LE -r 16000 -c 1 -t raw -
