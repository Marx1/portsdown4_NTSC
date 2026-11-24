#!/usr/bin/env bash
# Bounded, receive-only SRT-to-MPEG-TS preparation for the experimental
# 333 ksym/s, QPSK 1/2 DVB-S2 backend. Does not open a board or transmit RF.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: srt_dvbs2_ts_listener.sh --output FILE [--port PORT] [--duration SEC]

Accept one SRT caller and transcode to a 300 kbit/s MPEG-TS file with H.264
320x240/15 fps video and optional mono AAC audio. This stays below the current
backend's 329289 bit/s net rate at 333 ksym/s QPSK 1/2. Default port: 9000.
Default duration: 30 seconds. Does not transmit RF or key PTT.
EOF
}

port=9000
duration=30
output=
while (($#)); do
  case "$1" in
    --port|--duration|--output)
      (($# >= 2)) || { usage >&2; exit 2; }
      case "$1" in
        --port) port=$2;;
        --duration) duration=$2;;
        --output) output=$2;;
      esac
      shift 2;;
    -h|--help) usage; exit 0;;
    *) usage >&2; exit 2;;
  esac
done

[[ $port =~ ^[0-9]+$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || {
  echo 'port must be 1024-65535' >&2; exit 2;
}
[[ $duration =~ ^[0-9]+$ ]] && ((10#$duration >= 1 && 10#$duration <= 3600)) || {
  echo 'duration must be 1-3600 seconds' >&2; exit 2;
}
[[ -n $output && $output != -* ]] || { echo 'an output file is required' >&2; exit 2; }
[[ ! -e $output ]] || { echo "output already exists: $output" >&2; exit 2; }
command -v ffmpeg >/dev/null || { echo 'ffmpeg is required' >&2; exit 127; }

url="srt://0.0.0.0:${port}?mode=listener&latency=200000"
exec ffmpeg -hide_banner -loglevel info -nostdin -i "$url" \
  -t "$duration" -map 0:v:0 -map '0:a:0?' \
  -vf 'fps=15,scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2,format=yuv420p' \
  -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline \
  -bf 0 -g 30 -b:v 150000 -maxrate:v 150000 -bufsize:v 150000 \
  -c:a aac -b:a 32000 -ac 1 -ar 48000 \
  -mpegts_pmt_start_pid 4095 -streamid 0:4096 -muxrate 300000 \
  -f mpegts "$output"
