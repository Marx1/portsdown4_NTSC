#!/usr/bin/env bash
# Launch OBS with an isolated SRT-capable FFmpeg build, not system libraries.
set -euo pipefail

if (($# < 1)); then
  echo "Usage: $0 FFMPEG_PREFIX [OBS arguments ...]" >&2
  exit 2
fi
prefix=$1
shift
[[ -f "$prefix/lib/libavformat.so.58" ]] || {
  echo "FFmpeg 4.x shared libraries not found at $prefix/lib" >&2
  exit 2
}
if pgrep -u "$(id -u)" -x obs >/dev/null; then
  echo 'Close the existing OBS instance before launching the SRT profile.' >&2
  exit 1
fi
export LD_LIBRARY_PATH="$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec /usr/bin/obs "$@"
