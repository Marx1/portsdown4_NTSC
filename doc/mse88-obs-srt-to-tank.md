# MSE-88 OBS → SRT → TANK DATV test path

The bounded preview/capture path below prepares MPEG-TS files and checks
DVB-S2 modulation **offline**. It does not control DATV-Express USB, PTT, or
RF. A separate experimental [interlocked SRT TX](srt-interlocked-tx.md)
path is now available in the branch; it is not the preview/capture process.

The Portsdown touchscreen source menu in this branch now has an **SRT** entry
in the formerly unused second-row slot. Selecting it makes the main control
display read **Source: SRT** and persists `modeinput=SRT` across restarts and
presets. With **Express S2** output selected, pressing TX arms a separate live
listener without keying RF; it starts the experimental DVB-S2 backend only
after live video TS arrives and stops it on loss. Other SRT output selections
fail closed. TANK built the GUI but has no framebuffer, touchscreen, or
DATV-Express board, so physical/Web Control and RF behavior still need
testing. The preview cycle and TX listener cannot both bind port 9000.

## OBS profiles on MSE-88

MSE-88 runs OBS 29.1.3. Its system FFmpeg lacks SRT, so the DATV launchers
load the private SRT-enabled FFmpeg 4.2.7 from
`/home/mat/portsdown-srt/ffmpeg-4.2.7-srt-tls`. Close an existing OBS process
before using a launcher; it refuses to launch a second copy. With OBS already
open, select a DATV profile from OBS's **Profile** menu instead.

| OBS profile / launcher | Incoming SRT video | OBS encoder | Use |
| --- | --- | --- | --- |
| `DATV SRT TANK STREAM 480` / `start-obs-datv-480.sh` | nominal 854×480 (OBS emits 852×480), 24 fps, 600 kbit/s | native x264/AAC, 64 kbit/s audio | Source for DVB-S 480p or DVB-S2 480p |
| `DATV SRT TANK STREAM 720` / `start-obs-datv-720.sh` | 1280×720, 24 fps, 2,000 kbit/s | native x264/AAC, 96 kbit/s audio | Source for DVB-S2 720p |
| `DATV SRT TANK STREAM 1080` / `start-obs-datv-hd.sh` | 1920×1080, 15 fps, 3,500 kbit/s | native x264/AAC, 96 kbit/s audio | Source for DVB-S2 1080p |

All use OBS **Start Streaming**, **not Start Recording**, to send H.264/AAC
MPEG-TS to `srt://192.168.3.33:9000?mode=caller&latency=200000`. OBS's
native Streaming route uses `ffmpeg_mpegts_muxer`; it avoids the older Custom
FFmpeg Recording encoder path that crashed during Start/Stop tests. The
generic `start-obs-datv.sh` and `start-obs-datv-stream.sh` are 480p aliases.
Three application-menu entries say **OBS DATV SRT to TANK (Streaming ...)**.

Only these three clean DATV profiles and the untouched `BAM 2023` profile
remain in OBS's menu. The old `DATV SRT TANK`, `480`, `720`, and `HD` Custom
FFmpeg Recording profiles and their launchers were archived under
`/home/mat/portsdown-srt/obs-profile-backups/20261122-200640`, not deleted.
The profile setup is reproducible with
[`setup_mse_obs_datv_profiles.py`](../scripts/setup_mse_obs_datv_profiles.py)
while OBS is closed. Rebuilding OBS itself was not needed for this fix.

## TANK modes and procedure

[`srt_datv_ts_listener.py`](../scripts/srt_datv_ts_listener.py) receives one
SRT call, retains the input, transcodes to a rate-shaped TS, checks capacity
and timing, decodes the output, and—for DVB-S2—runs the standalone modulator
offline. It never keys RF. Supported profiles:

| Mode | Symbol rate | TS video/audio | FEC for capacity sizing |
| --- | ---: | --- | --- |
| DVB-S QPSK | 2,222,000 sym/s | MPEG-2/MP2, 720×480, 16:9 | 1/2, 2/3, 3/4, 5/6, 7/8 |
| DVB-S2 QPSK | 1,000,000 sym/s | H.264/AAC, 854×480, 1280×720, or 1920×1080 | 1/4, 1/3, 2/5, 1/2, 3/5, 2/3, 3/4, 4/5, 5/6, 8/9, 9/10 |

FEC is **not** encoded in the TS. The chosen FEC and symbol rate must match
the eventual modulator. At 1 Msym/s, 1080p has very low image quality even
when its TS passes validation.

Start a fresh bounded preview cycle on TANK **before** clicking Start
Streaming in OBS. Use a new output filename each time:

```sh
/home/leo/portsdown-srt/srt_datv_preview_cycle.sh \
  --mode dvbs2 --fec 1/2 --symbol-rate 1000000 --resolution 720p \
  --port 9000 --duration 120 --startup-grace 300 \
  --output /home/leo/portsdown-srt/obs-next-720.ts
```

For DVB-S, select the 480p OBS profile and change the TANK options to
`--mode dvbs --fec 1/2 --symbol-rate 2222000 --resolution 480p`. For DVB-S2
480p or 1080p, change both the OBS profile and `--resolution` accordingly.
`--duration` is the maximum received-video duration; `--startup-grace` allows
time to connect. Stop OBS Streaming when the test is complete. The preview
cycle is bounded: start a new cycle for the next SRT session. A separate
`--input-file` path on the listener can reprocess a retained source TS offline.

### Low-resolution encoder return from TANK to OBS

TANK's `tank-encoder-return.service` serves
`http://192.168.3.33:9013/return.ts`. Add that URL to an OBS **Media Source**
in a separate preview scene; turn off **Local File** and use `mpegts` if OBS
asks for a format. Do not put the return in the transmitted scene unless a
feedback loop is intended. It shows generated color bars with centered
**NO Signal YET!!!** text at rest, the **currently incoming SRT source**
during a preview cycle, then the generated card again when SRT packets stop
for four seconds or capture ends. The return is 426×240/15 fps H.264/AAC.
It never plays a saved TS recording. It is **not** a view of the shaped DVB-S2
TS, DATV-Express board, or received RF. OBS reconnects after source changes.

## Verified on 22 November 2026

Short Start/Stop Streaming tests from the three cleaned OBS profiles reached
TANK with decodable H.264/AAC. During each capture OBS reported zero skipped
frames and remained running. The captured sources and TANK outputs were:

| OBS source | Captured source TS | TANK output with FEC 1/2 | Result |
| --- | --- | --- | --- |
| 480p | 852×480, 12.125 s, 727 kbit/s | DVB-S MPEG-2/MP2 480p: 1,953,431 bit/s; DVB-S2 H.264/AAC 480p: 937,274 bit/s | Full decode; S2 offline modulation passed |
| 720p | 1280×720, 16.375 s, 2,199 kbit/s | DVB-S2 H.264/AAC 720p: 936,672 bit/s | Full decode and offline modulation passed |
| 1080p | 1920×1080, 16.667 s, 3,695 kbit/s | DVB-S2 H.264/AAC 1080p: 937,296 bit/s | Full decode and offline modulation passed |

The DVB-S 480p TS is below its 2,047,725 bit/s capacity; the DVB-S2 outputs
are below their 988,858 bit/s capacity. The real OBS source exposed a
`dts < pcr` error in the old DVB-S rate-shaping settings. TANK's MPEG-2 VBV
peak and TS mux headroom were corrected, and the rerun passed. These are
bounded **software** tests, not RF or decoded-receiver tests. Subjective
video/audio quality, long-duration stability, camera/ATEM input, and
DATV-Express USB/PTT/RF remain to be verified.

Separately, the 1080p ATEM-like fixture from
[`atem_srt_emulator.sh`](../scripts/atem_srt_emulator.sh) verified the live
HTTP return and its switch back to the waiting card. It is a transport test
fixture, not actual ATEM output.
