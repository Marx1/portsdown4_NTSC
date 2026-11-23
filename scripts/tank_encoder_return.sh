#!/usr/bin/env bash
# Live SRT confidence preview or generated waiting card; never replays a recording.
# This service has no RF/PTT control.
set -euo pipefail

bind=192.168.3.33
port=9013
mode_file=/home/leo/portsdown-srt/return-mode
live_url='udp://127.0.0.1:9014?fifo_size=100000&overrun_nonfatal=1&timeout=3000000'

usage() {
  echo 'Usage: tank_encoder_return.sh [--bind IP] [--port PORT] [--mode-file PATH] [--live-url UDP_URL]' >&2
}
while (($#)); do
  case "$1" in
    --bind|--port|--mode-file|--live-url)
      (($# >= 2)) || { usage; exit 2; }
      case "$1" in
        --bind) bind=$2;;
        --port) port=$2;;
        --mode-file) mode_file=$2;;
        --live-url) live_url=$2;;
      esac
      shift 2;;
    -h|--help) usage; exit 0;;
    *) usage; exit 2;;
  esac
done
[[ $port =~ ^[0-9]+$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || { usage; exit 2; }
[[ $bind =~ ^[0-9.]+$ && $live_url == udp://127.0.0.1:* ]] || { usage; exit 2; }
command -v ffmpeg >/dev/null || { echo 'FFmpeg is required' >&2; exit 127; }

url="http://${bind}:${port}/return.ts"
while :; do
  mode=$(cat "$mode_file" 2>/dev/null || echo card)
  if [[ $mode == live ]]; then
    echo "Serving current SRT input at $url" >&2
    input=(-i "$live_url" -map 0:v:0 -map '0:a:0?' \
           -vf 'fps=15,scale=426:240,format=yuv420p')
  else
    echo "Serving generated NO Signal YET!!! card at $url" >&2
    input=(-re -f lavfi -i 'testsrc2=size=426x240:rate=15' \
           -f lavfi -i 'anullsrc=r=48000:cl=mono' \
           -map 0:v:0 -map 1:a:0 \
           -vf "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='NO Signal YET!!!':fontcolor=white:fontsize=25:box=1:boxcolor=black@0.8:boxborderw=9:x=(w-text_w)/2:y=(h-text_h)/2,format=yuv420p")
  fi
  # HTTP handles one OBS client; after disconnect, reopen in the current mode.
  ffmpeg -hide_banner -loglevel error -nostdin "${input[@]}" \
    -c:v libx264 -preset ultrafast -tune zerolatency -b:v 220k \
    -maxrate:v 220k -bufsize:v 440k -g 30 \
    -c:a aac -b:a 32k -ac 1 -ar 48000 \
    -muxdelay 0.1 -f mpegts -listen 1 "$url" || :
  sleep 1
done
