# Trixie source/output porting scope

This is a development matrix, **not a 64-bit Trixie installation guide**.
TANK has built the earlier native AArch64 GUI/backend and passed offline SRT
tests, but there is no fresh 64-bit Portsdown install, touchscreen, or
DATV-Express board test. The latest local-source GUI changes have not yet
been rebuilt on TANK. The old Buster installer must not be used on Trixie.

## Express-first slice

`a.sh` routes the sources below through `express_capture_tx.py` when the
output/modulation is Express S2 QPSK, or when the original Express output is
DVB-S with `h264backend=ffmpeg`. This supervisor checks TS sync, PAT/PMT,
video packets, and preroll before starting the output. On capture end or a
two-second video stall, it stops the DVB-S2 backend or returns the DVB-S
server to receive. `--dry-run` does not open the board or assert PTT.

| Source | Modern capture | Configuration / current limit |
| --- | --- | --- |
| Pi Cam | `rpicam-vid` raw YUV to FFmpeg | Direct camera use on TANK is blocked by its rover; selected source requires Pi camera hardware test. |
| Composite/NTSC | V4L2 YUYV to FFmpeg | Set `analogcamname=/dev/videoN`; NTSC only. Device format, audio, and interlace need testing. |
| Webcam/C920 | V4L2 MJPEG if advertised, otherwise YUYV | Set `expresswebcamdevice=/dev/videoN`; actual format/raster and audio require device tests. The GUI now retains C920 selection for H.264. |
| HDMI capture | V4L2 to FFmpeg | Set `expresshdmidevice=/dev/videoN` for a Camlink-like device. This is **not** the network LKV HDMI path; audio device needs explicit configuration. |
| Test card | Explicit looped image to FFmpeg | `expresstestcard=/path/image.jpg` optional. It is a deliberately selected source, never a fallback for lost SRT. |
| SRT | `ipts_interlocked_tx.py` for Express DVB-S; `srt_interlocked_tx.py` for experimental DVB-S2 QPSK | Both listen for live MPEG-TS over SRT on port 9000; DVB-S transcodes to MPEG-2/MP2 480p. No saved-TS fallback. Actual ATEM output untested. |

Set `expressaudiodevice=hw:X,Y` (or another FFmpeg ALSA identifier) for
capture audio; without it the local-source TS is video-only. Set
`h264encoder=software`, `hardware`, or `auto` as appropriate. The selected
format sets the output raster; 720p/1080p at low symbol rates may produce a
very low video bitrate and are **not** validated as watchable profiles.
Unsupported sources fail explicitly in the new S2 route. Other original
Express DVB-S sources continue to use legacy paths until ported.

The first bounded test-card runs reached the live-video gate for DVB-S and
experimental S2 QPSK on the development host. The S2 run used a rate-only
backend stub and discarded TS; it did not verify modulation, USB, or RF.
The earlier real AArch64 backend I/Q and SRT checks are documented in
[arm64-transmitter.md](arm64-transmitter.md) and
[srt-interlocked-tx.md](srt-interlocked-tx.md).

## Remaining capture modes

1. Inventory every GUI `CurrentSource`/encoding/format combination against
   `a.sh` branches. Port PiScreen/desktop, contest/animated cards, LKV HDMI,
   IPTS input, TS file, and any network/file sources deliberately rather than
   mapping unknown inputs to a test card. Preserve explicit EOF and
   disconnect behavior; do not loop a recording after live input disappears.
2. Separate source acquisition from TS encoding. For each capture device,
   negotiate actual V4L2 formats/rates, HDMI audio or ALSA pairing, timestamps,
   interlace handling, and A/V sync. Measure 480p/720p/1080p latency and CPU
   on both 32-bit and 64-bit Pi 4.
3. Complete the Trixie installer, system dependencies, camera permissions,
   config migration, GUI display/touch/Web Control startup, and clean stop.
   A fresh OS image is the acceptance test; a clean repository clone is not.

## Remaining output modes

- **Pluto/LibreSDR:** Keep their independent DVB-S/S2 modulator and transport
  path. Port the legacy source-to-TS feed, rebuild with current `libiio` and
  USB/network dependencies, then verify firmware/API compatibility, frequency,
  sample rate, gain, PTT/mute, underrun, and receiver decode on hardware.
  Express raw-16 I/Q cannot be redirected to Pluto unchanged.
- **Streamer / IP Output:** These are now explicitly separate: Streamer keeps
  RTMP/FLV via `streamurl/streamkey`; IP Output offers direct UDP TS or an
  SRT TS bridge to another Pi's IPTS Monitor. See [link setup](ipts-srt-link.md).
  Replace Streamer's Buster capture assumptions, verify RTMP URL/auth and
  reconnect, and measure audio/video sync. The new SRT bridge does not make
  legacy IPTS-in-to-RF loss-interlocked.
- **Lime, native Pi RF, DVB-T/T2, Muntjac, Jetson, other outputs:** Audit each
  separate binary, architecture-specific build flags/assembly, libraries,
  firmware and GPIO/DMA assumptions. Port and test individually; a native
  compile is not a transmission test.

For each matrix cell, acceptance needs a fresh 32-bit or 64-bit Trixie boot,
GUI source selection, bounded encode/decode and A/V check, clean loss/stop,
then output-specific hardware and receiver tests. A DATV-Express board and
load/attenuated receiver are required before claiming DVB-S or S2 RF on the
new path. A touchscreen or 800×480 framebuffer is needed for GUI/Web Control
validation.
