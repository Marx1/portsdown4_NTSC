#!/usr/bin/env bash
# On TANK, show waiting bars until a bounded SRT capture becomes a validated TS.
# This controls only the HTTP confidence return; it never starts RF or PTT.
set -euo pipefail

base=/home/leo/portsdown-srt
listener="$base/srt_datv_ts_listener.py"
return_link="$base/current-encoded.ts"
waiting="$base/return-waiting.ts"
service=tank-encoder-return.service

usage() {
  cat >&2 <<'EOF'
Usage: srt_datv_preview_cycle.sh --mode dvbs2 --fec 1/2 --resolution 480p \
  --duration 120 --output /home/leo/portsdown-srt/new-capture.ts [listener options]

The HTTP return shows waiting color bars during capture and validation. Only a
successful listener validation switches it to the new saved TS. It is not a
live SRT or RF preview. A failed capture leaves the waiting bars visible.
EOF
}

output=
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case ${args[i]} in
    --output)
      ((i + 1 < ${#args[@]})) || { usage; exit 2; }
      output=${args[i+1]}
      ((i++)) || :
      ;;
    --output=*) output=${args[i]#--output=} ;;
  esac
done
[[ -n $output && $output = /* && -d $(dirname "$output") && ! -e $output ]] || {
  usage
  exit 2
}
[[ -f $listener ]] || { echo "Missing listener: $listener" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo 'FFmpeg is required' >&2; exit 127; }

if [[ ! -s $waiting ]]; then
  card_tmp="$base/.return-waiting.$$.ts"
  trap 'rm -f -- "$card_tmp"' EXIT
  ffmpeg -hide_banner -loglevel error -nostdin -y \
    -f lavfi -i 'testsrc2=size=854x480:rate=15' \
    -f lavfi -i 'anullsrc=r=48000:cl=mono' \
    -t 4 -map 0:v:0 -map 1:a:0 \
    -vf "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='NO Signal YET!!!':fontcolor=white:fontsize=46:box=1:boxcolor=black@0.8:boxborderw=18:x=(w-text_w)/2:y=(h-text_h)/2" \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p -b:v 300k \
    -c:a aac -b:a 32k -f mpegts "$card_tmp"
  mv -f -- "$card_tmp" "$waiting"
  trap - EXIT
fi

switch_return() {
  local target=$1
  local temp_link="$base/.current-encoded.$$.next"
  ln -s -- "$target" "$temp_link"
  mv -Tf -- "$temp_link" "$return_link"
  sudo -n systemctl restart "$service"
}

switch_return "$waiting"
echo "Waiting color bars on http://192.168.3.33:9013/return.ts" >&2
if python3 "$listener" "$@"; then
  [[ -s $output ]] || { echo 'Validator returned success without an output TS' >&2; exit 1; }
  switch_return "$output"
  echo "Validated TS is now on the low-resolution return: $output" >&2
else
  status=$?
  echo "Capture/validation failed; return remains on waiting color bars" >&2
  exit "$status"
fi
