#!/usr/bin/env bash
# Modern Pi Camera capture to constant-rate MPEG-TS. No RF or PTT control here.
set -euo pipefail

fail() { printf 'picam_ts_ffmpeg: %s\n' "$*" >&2; exit 2; }
source_input=rpicam
codec=h264
video_encoder=auto
output=
size=720x480
fps=30000/1001
video_bitrate=
muxrate=
pmt_pid=255
video_pid=256
audio_pid=257
service_id=1
service_name=Portsdown
audio_device=
audio_bitrate=48000
audio_channels=1
audio_rate=48000
rotation=0
duration=

while (($#)); do
  (($# >= 2)) || fail "missing value for $1"
  case "$1" in
    --source) source_input=$2;;
    --codec) codec=$2;;
    --video-encoder) video_encoder=$2;;
    --output) output=$2;;
    --size) size=$2;;
    --fps) fps=$2;;
    --video-bitrate) video_bitrate=$2;;
    --muxrate) muxrate=$2;;
    --pmt-pid) pmt_pid=$2;;
    --video-pid) video_pid=$2;;
    --audio-pid) audio_pid=$2;;
    --service-id) service_id=$2;;
    --service-name) service_name=$2;;
    --audio-device) audio_device=$2;;
    --audio-bitrate) audio_bitrate=$2;;
    --audio-channels) audio_channels=$2;;
    --audio-rate) audio_rate=$2;;
    --rotation) rotation=$2;;
    --duration) duration=$2;;
    *) fail "unknown option: $1";;
  esac
  shift 2
done

[[ "$codec" == h264 || "$codec" == mpeg2 ]] || fail 'codec must be h264 or mpeg2'
[[ "$size" =~ ^[0-9]+x[0-9]+$ ]] || fail 'size must be WIDTHxHEIGHT'
[[ "$fps" =~ ^[0-9]+(/[0-9]+)?$ ]] || fail 'fps must be a positive integer or fraction'
[[ "$rotation" == 0 || "$rotation" == 180 ]] || fail 'rotation must be 0 or 180'
[[ -n "$output" ]] || fail 'output is required'
for value in "$video_bitrate" "$muxrate" "$pmt_pid" "$video_pid" "$audio_pid" "$service_id" "$audio_bitrate" "$audio_channels" "$audio_rate"; do
  [[ "$value" =~ ^[0-9]+$ ]] || fail 'bitrate, PID, service, and audio values must be unsigned integers'
done
(( video_bitrate > 0 && muxrate > video_bitrate + 16000 )) || fail 'muxrate must exceed video bitrate'
(( pmt_pid >= 32 && pmt_pid <= 8189 && video_pid >= 32 && video_pid <= 8189 && audio_pid >= 32 && audio_pid <= 8189 )) || fail 'PID out of range'
(( pmt_pid != video_pid && pmt_pid != audio_pid && video_pid != audio_pid )) || fail 'PIDs must be distinct'
(( service_id >= 1 && service_id <= 65535 )) || fail 'service ID out of range'
(( audio_channels == 1 || audio_channels == 2 )) || fail 'audio channels must be 1 or 2'
if [[ -n "$audio_device" ]]; then
  (( muxrate > video_bitrate + audio_bitrate + 16000 )) || fail 'muxrate has insufficient room for audio'
fi
command -v ffmpeg >/dev/null || fail 'ffmpeg is required'

hardware_available() {
  command -v timeout >/dev/null 2>&1 || return 1
  timeout 10s ffmpeg -hide_banner -loglevel error -nostdin \
    -f lavfi -i "color=size=$size:rate=$fps" -frames:v 1 \
    -vf format=yuv420p -c:v h264_v4l2m2m -profile:v 66 -bf 0 \
    -b:v "$video_bitrate" -f h264 -y /dev/null >/dev/null 2>&1
}
if [[ "$codec" == h264 ]]; then
  case "$video_encoder" in
    software) ffmpeg_encoder=libx264;;
    hardware)
      hardware_available || fail 'hardware H.264 encoder cannot encode at this size/rate'
      ffmpeg_encoder=h264_v4l2m2m;;
    auto)
      if hardware_available; then ffmpeg_encoder=h264_v4l2m2m;
      else ffmpeg_encoder=libx264; fi;;
    *) fail 'video encoder must be software, hardware, or auto';;
  esac
  printf 'picam_ts_ffmpeg: using %s\n' "$ffmpeg_encoder" >&2
fi

width=${size%x*}
height=${size#*x}
capture_width=$(( (width + 31) / 32 * 32 ))
capture_height=$(( (height + 15) / 16 * 16 ))
capture_size=${capture_width}x${capture_height}
ffmpeg_args=(-hide_banner -loglevel warning -nostdin -thread_queue_size 1024)
case "$source_input" in
  rpicam)
    command -v rpicam-vid >/dev/null || fail 'rpicam-vid is required for Pi Camera capture'
    # rpicam-vid owns the modern libcamera path. Raw YUV avoids OMX/MMAL and
    # avoids a second lossy H.264 encode before the TS bitrate is applied.
    # Use aligned dimensions so raw camera row stride is unambiguous, then
    # crop the pad before the output-rate/size conversion.
    ffmpeg_args+=(-f rawvideo -pixel_format yuv420p -video_size "$capture_size" -framerate 30 -i pipe:0)
    ;;
  testsrc)
    ffmpeg_args+=(-f lavfi -i "testsrc2=size=$size:rate=30")
    ;;
  *)
    [[ -r "$source_input" ]] || fail "cannot read source: $source_input"
    ffmpeg_args+=(-i "$source_input")
    ;;
esac

if [[ -n "$audio_device" ]]; then
  if [[ "$audio_device" == testtone ]]; then
    ffmpeg_args+=(-f lavfi -i "sine=frequency=1000:sample_rate=$audio_rate")
  else
    ffmpeg_args+=(-thread_queue_size 1024 -f alsa -ac "$audio_channels" -ar "$audio_rate" -i "$audio_device")
  fi
fi

video_filter="fps=$fps,scale=${size/x/:}:flags=fast_bilinear,format=yuv420p"
if [[ "$source_input" == rpicam ]]; then
  video_filter="crop=${width}:${height},$video_filter"
fi
ffmpeg_args+=(-map 0:v:0 -vf "$video_filter" -r "$fps")
if [[ "$codec" == h264 ]]; then
  ffmpeg_args+=(-c:v "$ffmpeg_encoder" -g 60 -bf 0)
  if [[ "$ffmpeg_encoder" == libx264 ]]; then
    ffmpeg_args+=(-preset ultrafast -tune zerolatency -profile:v baseline)
  else
    ffmpeg_args+=(-profile:v 66)
  fi
else
  ffmpeg_args+=(-c:v mpeg2video -g 15 -bf 0)
fi
ffmpeg_args+=(-b:v "$video_bitrate" -maxrate:v "$video_bitrate" -bufsize:v "$video_bitrate")
if [[ -n "$audio_device" ]]; then
  if [[ "$codec" == h264 ]]; then audio_codec=aac; else audio_codec=mp2; fi
  ffmpeg_args+=(-map 1:a:0 -c:a "$audio_codec" -b:a "$audio_bitrate" -ac "$audio_channels" -ar 48000)
else
  ffmpeg_args+=(-an)
fi
ffmpeg_args+=(-metadata service_provider=Portsdown -metadata "service_name=$service_name"
  -mpegts_original_network_id 1 -mpegts_transport_stream_id 1
  -mpegts_service_id "$service_id" -mpegts_pmt_start_pid "$pmt_pid"
  -streamid "0:$video_pid")
if [[ -n "$audio_device" ]]; then ffmpeg_args+=(-streamid "1:$audio_pid"); fi
ffmpeg_args+=(-muxrate "$muxrate" -f mpegts)
if [[ -n "$duration" ]]; then ffmpeg_args+=(-t "$duration"); fi
ffmpeg_args+=(-y "$output")

if [[ "$source_input" == rpicam ]]; then
  # The pipeline propagates camera acquisition errors and FFmpeg failures.
  camera_timeout=0
  if [[ -n "$duration" ]]; then camera_timeout="${duration}s"; fi
  rpicam-vid --timeout "$camera_timeout" --nopreview --codec yuv420 --width "$capture_width" --height "$capture_height" \
    --framerate 30 --rotation "$rotation" --output - | ffmpeg "${ffmpeg_args[@]}"
else
  exec ffmpeg "${ffmpeg_args[@]}"
fi
