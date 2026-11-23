# MSE-88 OBS → SRT → TANK DVB-S2 test transport

This is an **ingest and offline modulation** setup, not RF transmission. An
MPEG transport stream is not intrinsically DVB-S2; its bitrate must fit the
chosen DVB-S2 mode before the modulator can use it continuously.

## Installed on 22 November 2026

- MSE-88 runs OBS 29.1.3 on Linux Mint 20.2. Its system FFmpeg 4.2.7 lacks
  the SRT protocol. A private FFmpeg 4.2.7 build with `--enable-libsrt` and
  `--enable-libx264` is at
  `/home/mat/portsdown-srt/ffmpeg-4.2.7-srt`. It does not replace system
  libraries. Its source and build records are under
  `/home/mat/portsdown-srt/ffmpeg-build`.
- A separate OBS profile, **DATV SRT TANK**, is installed. It uses Advanced →
  Recording → Custom Output (FFmpeg), MPEG-TS, H.264 at 640×360/600 kbit/s,
  and AAC at 64 kbit/s. Its destination is
  `srt://192.168.3.33:9000?mode=caller&latency=200000`. The original
  **BAM 2023** profile and running OBS process were not changed. The new
  profile has no inherited RTMP stream key.
- `/home/mat/portsdown-srt/start-obs-datv.sh` launches OBS with the private
  libraries and selects that profile. A desktop launcher named **OBS DATV SRT
  to TANK** is also installed. Close the existing OBS instance first; the
  launcher refuses to start a second instance.
- TANK has `/home/leo/portsdown-srt/srt_dvbs2_ts_listener.sh`. It listens for
  one SRT caller, transcodes to H.264 320×240/15 fps and optional mono AAC,
  and writes a bounded 300 kbit/s MPEG-TS file. That is below the experimental
  backend's reported 329,289 bit/s net rate at 333 ksym/s QPSK 1/2. The
  listener neither starts the transmitter nor keys PTT.

## Use

On TANK, start a bounded capture with a new filename:

```sh
/home/leo/portsdown-srt/srt_dvbs2_ts_listener.sh \
  --port 9000 --duration 60 \
  --output /home/leo/portsdown-srt/obs-test-001.ts
```

Then close the current OBS instance on MSE-88 and launch **OBS DATV SRT to
TANK**. Verify that the profile shown is **DATV SRT TANK**. Select the intended
scene and click **Start Recording**. OBS labels this button “Recording” even
though the custom FFmpeg output is a network SRT stream. Stop it before the
TANK capture timeout, then inspect the file on TANK:

```sh
ffprobe -v error -show_entries format=duration,bit_rate,size \
  -show_entries stream=codec_type,codec_name,width,height,r_frame_rate \
  -of json /home/leo/portsdown-srt/obs-test-001.ts
ffmpeg -v error -xerror -i /home/leo/portsdown-srt/obs-test-001.ts \
  -f null -
/home/leo/portsdown-express-s2-arm64/src/express_s2/express_s2 \
  --input /home/leo/portsdown-srt/obs-test-001.ts --symbol-rate 333000
```

The last command is **offline only** because it has no `--tx`; it verifies
that the MPEG-TS packets can feed the software DVB-S2 modulator. It does not
prove DATV-Express USB or RF output.

## Verification and remaining gate

With a synthetic H.264/AAC source on MSE-88, the private FFmpeg called TANK
directly over SRT. TANK's bounded output was 11.888 seconds, H.264 320×240
at 15 fps plus AAC, 299,838 bit/s. FFmpeg decoded it without error, no
`dts < pcr` warning appeared, and the standalone DVB-S2 backend consumed
2,370 TS packets offline (110 frames). `rover-web.service` remained active.

The **actual OBS scene has not yet been sent**: the existing OBS process must
be closed and relaunched with the private libraries. Once that is done, check
its real audio/video, sustained bitrate, and any scene-specific capture
issues. No board, firmware, PTT, or RF transmission was tested here.
