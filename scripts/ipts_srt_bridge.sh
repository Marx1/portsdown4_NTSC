#!/usr/bin/env bash
# Live MPEG-TS video/audio bridge for IP Output or IPTS Input. No RF/PTT.
set -euo pipefail

usage() {
  echo 'Usage: ipts_srt_bridge.sh --send --remote IPv4 --srt-port PORT --udp-port LOCAL_PORT [--pid-file FILE]' >&2
  echo '   or: ipts_srt_bridge.sh --receive --srt-port PORT --udp-port LOCAL_PORT [--pid-file FILE]' >&2
  exit 2
}

mode= remote= srt_port= udp_port= pid_file=/tmp/portsdown-ipts-srt-tx.pid
while (($#)); do
  case "$1" in
    --send) mode=send; shift;;
    --receive) mode=receive; shift;;
    --remote|--srt-port|--udp-port|--pid-file)
      (($# >= 2)) || usage
      case "$1" in
        --remote) remote=$2;;
        --srt-port) srt_port=$2;;
        --udp-port) udp_port=$2;;
        --pid-file) pid_file=$2;;
      esac
      shift 2;;
    *) usage;;
  esac
done
[[ $mode == send || $mode == receive ]] || usage
for port in "$srt_port" "$udp_port"; do
  [[ $port =~ ^[0-9]+$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || usage
done
if [[ $mode == send ]]; then
  [[ $remote =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || usage
  IFS=. read -r a b c d <<< "$remote"
  for octet in "$a" "$b" "$c" "$d"; do
    [[ $octet =~ ^[0-9]+$ ]] && ((10#$octet <= 255)) || usage
  done
fi
command -v ffmpeg >/dev/null || { echo 'FFmpeg is required' >&2; exit 127; }
ffmpeg -hide_banner -protocols | grep -qx '  srt' || {
  echo 'FFmpeg lacks SRT protocol support' >&2; exit 2;
}

exec 9>"$pid_file"
flock -n 9 || { echo 'IPTS SRT bridge already running' >&2; exit 1; }
printf '%s\n' "$$" >&9
child= stopping=0
shutdown() {
  stopping=1
  if [[ -n $child ]]; then
    kill -TERM "$child" 2>/dev/null || true
    # FFmpeg may be blocked in network I/O; bound shutdown and reap it.
    sleep 0.2
    kill -KILL "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
    child=
  fi
}
trap shutdown INT TERM
trap 'shutdown; : > "$pid_file"' EXIT

while (( ! stopping )); do
  if [[ $mode == send ]]; then
    input="udp://127.0.0.1:${udp_port}?fifo_size=1000000&overrun_nonfatal=1"
    output="srt://${remote}:${srt_port}?mode=caller&transtype=live&latency=200000"
  else
    input="srt://0.0.0.0:${srt_port}?mode=listener&transtype=live&latency=200000"
    output="udp://127.0.0.1:${udp_port}?pkt_size=1316"
  fi
  # Re-mux only the live first video and optional audio streams; never read
  # a recording or provide a test-card fallback after a connection is lost.
  ffmpeg -hide_banner -loglevel warning -nostdin -fflags +genpts \
    -probesize 1000000 -analyzeduration 1000000 -i "$input" \
    -map 0:v:0 -map '0:a:0?' -c copy -f mpegts \
    -muxdelay 0 -muxpreload 0 -flush_packets 1 "$output" &
  child=$!
  wait "$child" || true
  child=
  if (( ! stopping )); then
    echo 'IPTS SRT connection ended; waiting to reconnect' >&2
    sleep 1 & wait $! || true
  fi
done
