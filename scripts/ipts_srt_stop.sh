#!/usr/bin/env bash
# Stop only the bridge owned by this Portsdown TX session.
set -u
pidfile=${1:-/tmp/portsdown-ipts-srt-tx.pid}
[[ -r $pidfile ]] || exit 0
read -r pid < "$pidfile"
[[ $pid =~ ^[0-9]+$ ]] || exit 0
[[ -r /proc/$pid/cmdline ]] || exit 0
cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
[[ $cmdline == *ipts_srt_bridge.sh* ]] || exit 0
kill -TERM "$pid" 2>/dev/null || exit 0
for ((i=0; i<50; i++)); do
  kill -0 "$pid" 2>/dev/null || exit 0
  # An exited child can remain as a zombie until its parent reaps it.
  [[ -s /proc/$pid/cmdline ]] || exit 0
  sleep 0.1
done
echo 'IPTS SRT bridge did not stop within 5 seconds' >&2
exit 1
