#!/usr/bin/env bash
# Bounded ATEM-like H.264/AAC MPEG-TS sender over SRT. No OBS or RF required.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: atem_srt_emulator.sh [--url SRT_CALLER_URL] [--duration SEC]
                            [--fixture TS_FILE] [--ffmpeg-prefix DIR]

Generate a reusable 1080p29.97 H.264/AAC test pattern and tone (about 4 Mbit/s
video), then send it once in real time as MPEG-TS over SRT. Default destination:
srt://192.168.3.33:9000?mode=caller&latency=200000

This approximates the codecs, raster, and transport of an ATEM-like feed; it
does not claim to reproduce every model's SRT timestamps or settings.
EOF
}

url='srt://192.168.3.33:9000?mode=caller&latency=200000'
duration=15
fixture=
prefix="${HOME}/portsdown-srt/ffmpeg-4.2.7-srt-tls"
while (($#)); do
  case "$1" in
    --url|--duration|--fixture|--ffmpeg-prefix)
      (($# >= 2)) || { usage >&2; exit 2; }
      case "$1" in
        --url) url=$2;;
        --duration) duration=$2;;
        --fixture) fixture=$2;;
        --ffmpeg-prefix) prefix=$2;;
      esac
      shift 2;;
    -h|--help) usage; exit 0;;
    *) usage >&2; exit 2;;
  esac
done

[[ $duration =~ ^[0-9]+$ ]] && ((10#$duration >= 1 && 10#$duration <= 120)) || {
  echo 'duration must be 1-120 seconds' >&2; exit 2;
}
[[ $url == srt://* && $url == *mode=caller* ]] || {
  echo 'URL must be an SRT caller URL' >&2; exit 2;
}
fixture=${fixture:-"${HOME}/portsdown-srt/atem-like-1080p30-${duration}s.ts"}
[[ -d $(dirname "$fixture") ]] || { echo 'fixture directory does not exist' >&2; exit 2; }
[[ -x $prefix/bin/ffmpeg && -f $prefix/lib/libavformat.so.58 ]] || {
  echo 'private SRT-enabled FFmpeg prefix not found' >&2; exit 2;
}
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || {
  echo 'system ffmpeg and ffprobe are required to create the fixture' >&2; exit 127;
}

if [[ ! -e $fixture ]]; then
  echo "Creating ATEM-like test fixture: $fixture"
  ffmpeg -hide_banner -loglevel warning -nostdin -n \
    -f lavfi -i 'testsrc2=size=1920x1080:rate=30000/1001' \
    -f lavfi -i 'sine=frequency=440:sample_rate=48000' \
    -t "$duration" -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
    -b:v 4000k -maxrate:v 4000k -bufsize:v 8000k -g 60 \
    -c:a aac -b:a 128k -ac 2 -ar 48000 -f mpegts "$fixture"
fi
[[ -s $fixture ]] || { echo "fixture missing or empty: $fixture" >&2; exit 1; }
ffprobe -v error -show_entries format=duration,bit_rate \
  -show_entries stream=codec_name,width,height -of compact "$fixture"
echo "Sending $fixture to $url in real time"
export LD_LIBRARY_PATH="$prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$prefix/bin/ffmpeg" -hide_banner -loglevel warning -nostdin \
  -re -i "$fixture" -t "$duration" -map 0:v:0 -map '0:a:0?' \
  -c copy -f mpegts "$url"
