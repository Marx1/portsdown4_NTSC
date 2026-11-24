#!/bin/bash
# Stop only the interlocked TX supervisor; it deinitializes its backend first.
set -u
pidfile=/tmp/portsdown-srt-tx.pid
[[ -r $pidfile ]] || exit 0
read -r pid < "$pidfile"
[[ $pid =~ ^[0-9]+$ ]] || exit 0
[[ -r /proc/$pid/cmdline ]] || exit 0
cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
[[ $cmdline == *srt_interlocked_tx.py* || $cmdline == *express_capture_tx.py* || $cmdline == *ipts_interlocked_tx.py* ]] || exit 0
kill -TERM "$pid" 2>/dev/null || exit 0
for ((i=0; i<50; i++)); do
  kill -0 "$pid" 2>/dev/null || exit 0
  sleep 0.1
done
echo "SRT TX supervisor did not stop within 5 seconds" >&2
exit 1
