# MSE-88 OBS → SRT → TANK DVB-S2 test transport

This is an **ingest and offline modulation** setup, not RF transmission. An
MPEG transport stream is not intrinsically DVB-S2; its bitrate must fit the
chosen DVB-S2 mode before the modulator can use it continuously.

## Installed on 22 November 2026

- MSE-88 runs OBS 29.1.3 on Linux Mint 20.2. Its system FFmpeg 4.2.7 lacks
  the SRT protocol. A private FFmpeg 4.2.7 build with SRT, HTTPS, and x264 is
  at `/home/mat/portsdown-srt/ffmpeg-4.2.7-srt-tls`. It does not replace system
  libraries or packages. It was built locally with OpenSSL and GPL x264, so
  the resulting binary is not for redistribution. Source and build records are under
  `/home/mat/portsdown-srt/ffmpeg-build`.
- A separate OBS profile, **DATV SRT TANK**, is installed. It uses Advanced →
  Recording → Custom Output (FFmpeg), MPEG-TS, H.264 at 640×360/600 kbit/s,
  and AAC at 64 kbit/s. Its destination is
  `srt://192.168.3.33:9000?mode=caller&latency=200000`. The original
  **BAM 2023** profile was preserved byte-for-byte. OBS was restarted with
  the new profile selected. The new profile has no inherited RTMP stream key.
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

On MSE-88, close any existing OBS instance and launch **OBS DATV SRT to TANK
(Streaming 480p)**. Verify the **DATV SRT TANK STREAM 480** profile is selected.
Select the intended scene and click **Start Streaming**. This native-encoder
SRT path is the tested workaround for crashes in the older Custom FFmpeg
Recording profiles; see the diagnosis below. Stop Streaming before the TANK
capture timeout, then inspect the file on TANK:

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

The actual OBS scene was then streamed for a short bounded test through the
new profile. OBS's FFmpeg output started and stopped successfully. TANK
captured 10.821 seconds of H.264 320×240/15 fps plus AAC in a 300,068 bit/s
TS file at `/home/leo/portsdown-srt/obs-live-probe.ts`. FFmpeg decoded the
file without error; the standalone DVB-S2 backend consumed all 2,159 TS
packets offline (101 frames). The SRT input logged an input/output error when
OBS disconnected at the end, but the saved file is decodable. No `dts < pcr`
warning appeared. The original profile checksums still matched and TANK's
rover service remained active.

The test establishes the **OBS → SRT → TANK → TS → offline DVB-S2 I/Q**
path for a short run. Longer-running stability, real audio/video quality,
scene-specific capture sources, DATV-Express USB, firmware, PTT, and decoded
RF output remain unverified. No RF transmission was enabled.

## Target modes added 22 November 2026

`scripts/srt_datv_ts_listener.py` is a separate bounded TS-preparation tool
installed on TANK at `/home/leo/portsdown-srt/srt_datv_ts_listener.py`. It does
not replace the earlier 333 ksym/s listener. The requested targets are:

| Mode | Symbol rate | Video | Audio | FEC accepted for TS sizing |
| --- | ---: | --- | --- | --- |
| DVB-S QPSK | 2,222,000 sym/s | MPEG-2, 720×480 progressive, 16:9 display | MP2 | 1/2, 2/3, 3/4, 5/6, 7/8 |
| DVB-S2 QPSK | 1,000,000 sym/s | H.264, 854×480, 1280×720, or 1920×1080 progressive | AAC | 1/4, 1/3, 2/5, 1/2, 3/5, 2/3, 3/4, 4/5, 5/6, 8/9, 9/10 |

The FEC is **not in the TS file**: it must match the downstream modulator.
For DVB-S, the tool computes QPSK transport capacity with 188/204 RS overhead.
For DVB-S2, it asks the local `express_s2 --rate-only` backend for exact
QPSK capacity. It sizes video and fixed-rate TS below capacity, then rejects
captures whose measured TS rate exceeds capacity or whose muxer reports
`dts < pcr`. Selecting a FEC does not by itself configure Portsdown's GUI or
key RF. At 1 Msym/s, low FEC rates leave very little room for 720p/1080p;
those selections can yield poor quality or fail the TS-timing check.

On TANK, start one listener **before** clicking **Start Streaming** in the new
OBS profile:

```sh
python3 /home/leo/portsdown-srt/srt_datv_ts_listener.py \
  --mode dvbs --fec 1/2 --resolution 480p --duration 60 \
  --output /home/leo/portsdown-srt/dvbs-480-001.ts

# Or, on a separate run, for DVB-S2:
python3 /home/leo/portsdown-srt/srt_datv_ts_listener.py \
  --mode dvbs2 --fec 1/2 --resolution 480p --duration 60 \
  --output /home/leo/portsdown-srt/dvbs2-480-001.ts
```

Use a fresh output name on every run and stop OBS streaming before the
listener duration. `--resolution 720p` or `1080p` selects the other S2
rasters; `--symbol-rate` can override the default. Offline DVB-S2 modulation
with the **same** FEC and symbol rate can be checked without RF:

```sh
/home/leo/portsdown-express-s2-arm64/src/express_s2/express_s2 \
  --input /home/leo/portsdown-srt/dvbs2-480-001.ts \
  --symbol-rate 1000000 --fec 1/2
```

MSE-88 has separate `DATV SRT TANK 480`, `DATV SRT TANK 720`, and
`DATV SRT TANK HD` OBS profiles and matching desktop launchers. Their ingest
settings are 854×480/1.2 Mbit/s, 1280×720/2 Mbit/s, and native 1920×1080/
4 Mbit/s respectively. The original `BAM 2023` profile was not changed.
The profile was restored to `DATV SRT TANK` after probing; it is the earlier
640×360/600 kbit/s profile. At the final check, a desktop-launched OBS instance
was running with **system FFmpeg**, not the private SRT-enabled libraries; it
was left untouched. Close OBS before using a DATV launcher, then verify the
SRT-enabled FFmpeg libraries are loaded. The 480, 720, and HD profiles are
opt-in experiments, not validated operational presets.

### What was verified and what remains broken

- TANK built the updated native `express_s2` backend. `--rate-only` returned
  positive capacities for all eleven listed S2 FEC rates at 1 Msym/s; the
  offline backend still needs USB/RF testing with a DATV-Express board.
- Synthetic MSE-88 SRT → TANK TS tests passed for DVB-S MPEG-2/MP2 480p at
  2222 ksym/s FEC 1/2 (1,911,250 bit/s, below 2,047,725 capacity) and DVB-S2
  H.264/AAC 480p at 1000 ksym/s FEC 1/4 (final-revision file: 467,276 bit/s,
  below 490,243 capacity). The files decoded. The S2 1/4 file also passed
  offline I/Q modulation in an earlier probe of the same profile.
- A real OBS scene reached TANK and decoded at S2 480p and 720p FEC 1/2, but
  FFmpeg reported `dts < pcr`; those TS files are **not validated**. The
  1080p synthetic probe also initially exceeded FEC 1/2 capacity. Later
  1080p rate shaping stayed below capacity in a short synthetic run, but
  source/encoder throughput and real-scene timing were not sustained.
- Repeated recordings with the new 480/HD OBS profiles caused MSE-88 OBS to
  segfault in the private FFmpeg `libavcodec.so.58` path. This needs debugging
  before using those profiles unattended. The profile was reset to
  `DATV SRT TANK`; a subsequent desktop OBS launch used system libraries.
  TANK's rover service remained active. No RF transmission was attempted.

## Repeatable ATEM-like SRT test (22 November 2026)

The OBS Custom FFmpeg Recording 480/HD crashes above are **not fixed**. For a repeatable transport test
without touching the running OBS instance, `scripts/atem_srt_emulator.sh` sends
one bounded H.264/AAC MPEG-TS fixture from MSE-88 using its private SRT-enabled
FFmpeg. The generated source is 1920×1080 at 30000/1001 fps, roughly 4 Mbit/s
H.264 video plus 128 kbit/s AAC and a test pattern/tone. This is **ATEM-like**,
not an exact emulation of any particular ATEM model or its SRT timestamps.
The actual ATEM output still needs capture and comparison.

`scripts/srt_datv_ts_listener.py` now receives the SRT call into a retained
`*.ingest.ts` file **first**, then probes and transcodes that local file. This
separates network arrival timing from slow 720p/1080p encoding. It is a bounded
file-production workflow, **not continuous live TS forwarding**. By default it
keeps the source capture alongside the output; `--input-file` can reprocess that
capture at another resolution/FEC without repeating the network transfer.
The script rejects an existing output path so test files are not overwritten.

Start TANK first (choose a fresh output filename):

```sh
python3 /home/leo/portsdown-srt/srt_datv_ts_listener.py \
  --mode dvbs2 --symbol-rate 1000000 --fec 1/2 --resolution 480p \
  --port 9000 --duration 20 \
  --output /home/leo/portsdown-srt/atem-test-001.ts
```

Then on MSE-88, in a separate shell:

```sh
/home/mat/portsdown-srt/atem_srt_emulator.sh \
  --url 'srt://192.168.3.33:9000?mode=caller&latency=200000' \
  --duration 15
```

This creates `atem-test-001.ingest.ts` and then `atem-test-001.ts` on TANK.
For another profile without another SRT call, use the same listener with
`--input-file /home/leo/portsdown-srt/atem-test-001.ingest.ts`, a different
`--resolution`/`--fec`, and a **new** `--output` filename. The listener sizes
the fixed-rate mux below the DVB-S2 backend's reported capacity, detects
FFmpeg `dts < pcr` warnings, checks packet alignment/codec/raster/audio,
fully decodes the TS, and feeds it through `express_s2` **offline** at the
selected symbol rate/FEC. A zero exit status means those checks passed, not
that RF transmission was tested. The FEC and symbol rate must match the later
hardware modulator; they are not carried inside the TS.

The fresh 15-second MSE-88 → SRT → TANK run at 1 Msym/s, QPSK FEC 1/2 yielded
14.744 seconds of 480p H.264/AAC TS at 938,956 bit/s, below the backend's
988,858 bit/s TS capacity. The automated checks passed, and the offline
modulator consumed 9,205 TS packets in 430 DVB-S2 frames. Reprocessing the
saved source at 720p and 1080p passed those same checks at 938,301 and
938,606 bit/s, respectively. Earlier bounded runs from the same source also
decoded and modulated offline at 480p/720p/1080p FEC 1/4 and 1080p FEC 9/10;
the complete matrix has **not** been tested through the final automated
validator. At 1 Msym/s, 1080p and low-FEC modes have very limited image
quality despite valid transport timing and codec decodability.

Still needed: a real ATEM capture; sustained/live forwarding if required;
visual/audio quality assessment on a receiver; and DATV-Express USB, firmware,
PTT, and decoded RF tests with hardware.

Neither the test sender nor the listener starts RF. TANK's rover service was
left running.

## OBS crash diagnosis and native SRT streaming workaround (22 November 2026)

Two MSE-88 OBS 29.1.3 core dumps from repeated **Start/Stop Recording** in the
480/HD Custom Output (FFmpeg) profiles have the same signature: a null
`reordered_opaque` array in FFmpeg 4.2.7's `libx264` wrapper during encode,
after OBS begins stopping the output. OBS's `ffmpeg_output_full_stop()` starts
asynchronous capture shutdown but immediately deactivates/frees its FFmpeg
video context. That is consistent with an encode/shutdown race; the exact
trigger has not been proven. The crashes are **not** caused by mixed system and
private FFmpeg libraries: the crashed OBS processes mapped all FFmpeg libraries
from the private build. Rebuilding OBS alone is not established as a fix.

OBS 29.1.3 has a different path for SRT **Streaming**: the `ffmpeg_mpegts_muxer`
uses OBS's native x264/AAC encoders and FFmpeg for MPEG-TS muxing and SRT
transport, bypassing the crashing FFmpeg `libx264` encoder path. On MSE-88, a
separate **DATV SRT TANK STREAM 480** profile and **OBS DATV SRT to TANK
(Streaming 480p)** launcher select this route. The launcher is
`/home/mat/portsdown-srt/start-obs-datv-stream.sh`; it still requires closing
the existing OBS instance first so the private SRT-enabled FFmpeg libraries
are used. The original profiles and launchers are unchanged. In this new
profile, click **Start Streaming**, *not* Start Recording. The destination is
`srt://192.168.3.33:9000?mode=caller&latency=200000`, with 600 kbit/s H.264
and 64 kbit/s AAC. OBS aligned the nominal 854x480 output to 852x480; TANK's
listener scales it to the requested 854x480 DVB-S2 TS raster.

The isolated native-stream profile passed three successive Start/Stop Streaming
cycles to local SRT listeners. Each capture contained decodable H.264/AAC; OBS
remained alive and produced no new core dump. A separate 10-second MSE-88 →
TANK SRT run then yielded a 9.906-second H.264/AAC 854x480 TS at 935,388
bit/s, below the DVB-S2 QPSK 1 Msym/s FEC 1/2 capacity of 988,858 bit/s.
TANK's validator decoded it and the standalone modulator consumed 6,161 TS
packets in 288 frames **offline**. The input reported an I/O error when OBS
disconnected, but the completed TS passed validation. This tested a blank
OBS scene, not a camera/ATEM scene or RF output. Longer runs and the 720p/HD
native-stream profiles remain untested.

## Low-resolution encoder return from TANK to OBS

TANK now has a separate `tank-encoder-return.service` on
`http://192.168.3.33:9013/return.ts`. It loops a **saved, validated TS file**
and re-encodes it as 426×240/15 fps H.264 with mono AAC at roughly 300 kbit/s.
The source is currently `atem-live-verified-480-fec12.ts`, selected via
`/home/leo/portsdown-srt/current-encoded.ts`. This is an encoded-output
**confidence return**, not a live view of the current encoder, SRT arrival,
DATV-Express board, or received RF signal. It does not start a transmitter.
The service accepts one viewer at a time and reopens the listener after a
viewer disconnects. It is independent of `rover-web.service`.

On MSE-88 OBS, add a **Media Source** to a separate preview scene. Uncheck
**Local File**, enter `http://192.168.3.33:9013/return.ts`, and, if OBS asks
for an input format, use `mpegts`. Leave the existing output profile alone.
Avoid placing the return in the scene being sent back to TANK unless a video
feedback loop is intended. MSE-88's **system FFmpeg** successfully captured
and decoded 5 seconds from the running service as H.264 426×240/15 fps plus
AAC, around 331 kbit/s. A 20-second capture crossed the source file loop
point and decoded, and a second client connection succeeded. The actual OBS
Media Source GUI has **not** yet been checked.

To preview another **already validated** TS file, point the symlink at it and
restart the service, then refresh the OBS Media Source:

```sh
cd /home/leo/portsdown-srt
ln -s /absolute/path/to/validated-output.ts current-encoded.next
mv -Tf current-encoded.next current-encoded.ts
sudo systemctl restart tank-encoder-return.service
systemctl is-active tank-encoder-return.service
```

The source file must remain on TANK while it is served. The service is enabled
for boot and its unit is in `scripts/tank-encoder-return.service`; the server
is `scripts/tank_encoder_return.sh`. Change or stop only that service; the
rover and SRT ingest run separately.
