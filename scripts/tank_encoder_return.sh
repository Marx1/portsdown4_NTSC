#!/usr/bin/env bash
# Serve a low-resolution confidence return from a local encoded TS file.
# This only reads files and opens an HTTP output; it never controls RF/PTT.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: tank_encoder_return.sh --input VALIDATED_TS [--bind IP] [--port PORT]

Loop a TANK MPEG-TS output as a 426x240/15 fps H.264 + mono AAC HTTP stream.
OBS Media Source URL: http://TANK_IP:PORT/return.ts
One OBS/client connection at a time; the server reopens after disconnect.
This is a confidence preview of a saved file, not a live encoder or RF receive.
EOF
}

input=
bind=192.168.3.33
port=9013
while (($#)); do
  case "$1" in
    --input|--bind|--port)
      (($# >= 2)) || { usage >&2; exit 2; }
      case "$1" in
        --input) input=$2;;
        --bind) bind=$2;;
        --port) port=$2;;
      esac
      shift 2;;
    -h|--help) usage; exit 0;;
    *) usage >&2; exit 2;;
  esac
done

[[ -n $input && -s $input ]] || { echo 'a nonempty --input TS file is required' >&2; exit 2; }
[[ $port =~ ^[0-9]+$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || {
  echo 'port must be 1024-65535' >&2; exit 2;
}
[[ $bind =~ ^[0-9.]+$ ]] || { echo 'bind must be a numeric IPv4 address' >&2; exit 2; }
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || {
  echo 'ffmpeg and ffprobe are required' >&2; exit 127;
}
codec=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name \
  -of default=noprint_wrappers=1:nokey=1 "$input" | sed -n '1p')
[[ $codec == h264 || $codec == mpeg2video ]] || {
  echo "unsupported input video codec: $codec" >&2; exit 2;
}

url="http://${bind}:${port}/return.ts"
echo "Serving $(realpath "$input") as 426x240 H.264/AAC at $url" >&2
while :; do
  # Each client gets fresh timestamps and a fresh file playback. A normal OBS
  # disconnect makes FFmpeg exit with a broken pipe; reopen the socket.
  ffmpeg -hide_banner -loglevel error -nostdin -re -stream_loop -1 -i "$input" \
    -map 0:v:0 -map '0:a:0?' -vf 'fps=15,scale=426:240,format=yuv420p' \
    -c:v libx264 -preset ultrafast -tune zerolatency -b:v 220k \
    -maxrate:v 220k -bufsize:v 440k -g 30 \
    -c:a aac -b:a 32k -ac 1 -ar 48000 \
    -muxdelay 0.1 -f mpegts -listen 1 "$url" || :
  sleep 1
done
