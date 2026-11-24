# First run on a fresh 32-bit Trixie Pi 4

This is an **isolated source and camera test**, not a Portsdown installation.
The legacy `install_portsdown.sh` and `update.sh` are for 32-bit Buster; do not
run either on Trixie. No service, boot setting, apt source, or RF output is
changed by the steps below. Use a spare SD card and keep the working Portsdown
installation intact.

## 1. Fetch this development branch

On the Pi, with Raspberry Pi OS Trixie **32-bit** booted and networking ready:

```sh
cat /etc/os-release | grep -E 'PRETTY_NAME|VERSION_CODENAME'
dpkg --print-architecture
sudo apt update
sudo apt install -y git ffmpeg v4l-utils usbutils python3
git clone --branch arm64-transmitter --single-branch \
  https://github.com/mathisono/portsdown4_NTSC.git \
  "$HOME/portsdown4-trixie-test"
cd "$HOME/portsdown4-trixie-test"
git rev-parse --short HEAD
```

Continue only if the OS codename is `trixie` and the architecture is `armhf`.
The branch name includes `arm64`, but it also contains the 32-bit NTSC/Trixie
development work. Do not substitute the older `Bookworm` installer.

## 2. Inventory the screen, camera, and encoder

```sh
bash scripts/trixie_probe.sh | tee "$HOME/portsdown-trixie-probe.txt"
v4l2-ctl --list-devices
```

Find the C920 capture node from the list (it may not be `/dev/video0`). Set
`CAM` to that node and inspect the modes it actually reports:

```sh
CAM=/dev/video0
v4l2-ctl -d "$CAM" --list-formats-ext
```

The C920 variants differ. If this camera reports MJPEG but not YUYV at the
desired size/rate, use its reported MJPEG mode. A camera offering MJPEG does
not, by itself, prove that Pi hardware H.264 encoding works. The probe's
one-frame encode checks that separately.

## 3. Check the MPEG-TS path without camera or RF

```sh
python3 tests/test_h264_ts_ffmpeg.py
```

This exercises NTSC/PAL H.264 transport streams and AAC with synthetic input.
It does not test the touchscreen, camera, transmitter, or full installer.

## 4. Capture a short C920 MJPEG sample to a file

Change `CAM`, `--capture-size`, and `--capture-rate` to a combination shown by
`--list-formats-ext`. Start with software H.264 encoding to separate camera
capture from the Pi hardware-encoder question:

```sh
scripts/h264_ts_ffmpeg.sh \
  --source "$CAM" --input-format mjpeg \
  --capture-size 640x480 --capture-rate 30 \
  --video-encoder software --standard ntsc \
  --video-bitrate 800000 --muxrate 1200000 \
  --duration 10 --output "$HOME/c920-ntsc-test.ts"
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 "$HOME/c920-ntsc-test.ts"
ffmpeg -v error -xerror -i "$HOME/c920-ntsc-test.ts" -f null -
```

If this succeeds, repeat with `--video-encoder auto` and a different output
filename to see whether the real Pi hardware encoder works or the script
falls back to `libx264`. Neither result proves RF transmission. Audio input
should be added only after video capture is stable and the correct ALSA device
has been identified.

Please retain the probe file, `v4l2-ctl` format list, the script's terminal
output, and the exact Git commit. These distinguish an unsupported camera
mode from an unavailable H.264 encoder or a transport-stream problem. The
full Trixie install, touchscreen GUI, and RF chain remain separate work.
