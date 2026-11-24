#!/usr/bin/env bash
# Preview incoming SRT live, then return to generated waiting bars on disconnect.
# The listener still retains and validates TS offline, but never plays it back.
# No RF/PTT control.
set -euo pipefail

base=/home/leo/portsdown-srt
listener="$base/srt_datv_ts_listener.py"
mode_file="$base/return-mode"
service=tank-encoder-return.service
preview_udp='udp://127.0.0.1:9014?pkt_size=1316'
end_marker="$base/.preview-end.$$"
listener_pid=

usage() {
  cat >&2 <<'EOF'
Usage: srt_datv_preview_cycle.sh --mode dvbs2 --fec 1/2 --resolution 480p \
  --duration 120 --output /home/leo/portsdown-srt/new-capture.ts [listener options]

The HTTP return shows generated NO Signal YET!!! bars, changes to the current
SRT video while it arrives, then returns to bars when SRT capture ends. Saved
TS output is validated offline but never played on the return.
EOF
}

output=
ingest=
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case ${args[i]} in
    --output|--ingest-file)
      ((i + 1 < ${#args[@]})) || { usage; exit 2; }
      if [[ ${args[i]} == --output ]]; then output=${args[i+1]}; else ingest=${args[i+1]}; fi
      ((i++)) || : ;;
    --output=*) output=${args[i]#--output=} ;;
    --ingest-file=*) ingest=${args[i]#--ingest-file=} ;;
    --input-file|--input-file=*|--preview-udp|--preview-udp=*|--preview-end-file|--preview-end-file=*)
      echo 'Input-file and internal preview options are not accepted by this live wrapper' >&2
      exit 2;;
  esac
done
[[ -n $output && $output = /* && $output == *.ts && -d $(dirname "$output") && ! -e $output ]] || { usage; exit 2; }
if [[ -z $ingest ]]; then
  ingest="${output%.ts}.ingest.ts"
fi
[[ ! -e $ingest ]] || { echo "Ingest path exists: $ingest" >&2; exit 2; }
[[ -f $listener ]] || { echo "Missing listener: $listener" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo 'FFprobe is required' >&2; exit 127; }
command -v setsid >/dev/null || { echo 'setsid is required' >&2; exit 127; }

exec 9>"$base/.preview-cycle.lock"
flock -n 9 || { echo 'A preview cycle is already running' >&2; exit 1; }

switch_mode() {
  local mode=$1 temp="$base/.return-mode.$$.next"
  printf '%s\n' "$mode" > "$temp"
  mv -f -- "$temp" "$mode_file"
  sudo -n systemctl restart "$service"
}

cleanup() {
  if [[ -n $listener_pid ]] && kill -0 "$listener_pid" 2>/dev/null; then
    kill -- "-$listener_pid" 2>/dev/null || :
    wait "$listener_pid" 2>/dev/null || :
  fi
  rm -f -- "$end_marker"
  if [[ $(cat "$mode_file" 2>/dev/null || :) != card ]]; then
    switch_mode card || echo 'Failed to restore waiting card' >&2
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

switch_mode card
echo 'Waiting card on http://192.168.3.33:9013/return.ts' >&2
setsid python3 "$listener" "$@" --preview-udp "$preview_udp" \
  --preview-end-file "$end_marker" &
listener_pid=$!
live=0
last_size=0
last_progress=$SECONDS
while [[ ! -e $end_marker ]] && kill -0 "$listener_pid" 2>/dev/null; do
  size=0
  if [[ -f $ingest ]]; then size=$(stat -c %s "$ingest"); fi
  if ((size > last_size)); then last_progress=$SECONDS; fi
  if ((live == 0 && size >= 188000 && size > last_size)); then
    # FFmpeg has already parsed a video stream and emitted at least 1000 TS packets.
    switch_mode live
    echo 'Live incoming SRT is on the low-resolution return' >&2
    live=1
  fi
  if ((live == 1 && SECONDS - last_progress >= 4)); then
    switch_mode card
    echo 'SRT packets stopped; waiting card restored' >&2
    live=0
  fi
  last_size=$size
  sleep 0.25
done
switch_mode card
echo 'SRT capture stopped; waiting card restored (no recording playback)' >&2
if wait "$listener_pid"; then
  listener_pid=
  echo "Saved TS validated offline: $output" >&2
else
  status=$?
  listener_pid=
  echo 'Capture/validation failed; waiting card remains visible' >&2
  exit "$status"
fi
