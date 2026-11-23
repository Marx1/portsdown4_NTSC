# Experimental SRT-interlocked DATV-Express DVB-S2 TX

The touchscreen now has **Output Device → Express S2** (separate from the
working **Express** DVB-S mode). Select **Source → SRT**, **Modulation → S2
QPSK**, a DVB-S2 FEC, symbol rate, frequency, and output format. Pressing TX
**arms** an SRT listener on UDP 9000. It does not assert PTT while waiting.
The transmitter backend starts only after the live, rate-shaped TS has PAT,
PMT, at least 30 video packets, and 500 TS packets. A disconnect, invalid TS,
or two-second video-packet stall stops the backend. The backend also has a
two-second input timeout in its hardware transmit mode. The GUI resets its
armed TX indication when the supervisor exits. No saved TS or test card is
used as RF fallback.

The first integrated path supports **DATV-Express raw-16, DVB-S2 QPSK, normal
frames, pilots off, 35% rolloff**, with GUI FEC selection. SRT video is
transcoded to H.264/AAC and a TS mux rate below the selected DVB-S2 capacity.
Other output devices and modulation modes are not silently substituted. The
legacy `DATVEXPRESS` DVB-S mode is unchanged. On a Portsdown installation,
build/install both `src/gui/rpidatvgui` and `src/express_s2/express_s2`, then
install the changed scripts under `/home/pi/rpidatv/scripts/`; the GUI uses
those absolute paths. Do **not** run the old Buster installer on Trixie.

## Offline interlock test

Use `--dry-run` and a separate port to exercise the source gate **without
opening the board or keying RF**. The config file must contain
`modeinput=SRT`, `modeoutput=DATVEXPRESS_S2`, `modulation=S2QPSK`, `fec=12`,
`symbolrate=1000`, `freqoutput=437`, and `format=16:9` (other supported values
may be substituted). For example:

```sh
python3 scripts/srt_interlocked_tx.py \
  --config /path/to/test-config.txt \
  --backend /path/to/src/express_s2/express_s2 \
  --port 19001 --pid-file /tmp/portsdown-srt-test.pid --dry-run
```

Before a caller connects, the log says `Armed ... RF off` and no backend
process exists. Send an H.264/AAC MPEG-TS SRT caller to that port; the log
then reports `Valid live SRT TS`. Stopping the caller or stalling its packet
flow must produce `SRT TX stopped`. The existing preview cycle also listens
on 9000; stop it before running this TX path on the normal port. This TX
supervisor does not yet switch TANK's low-resolution return service.

## Verification and remaining hardware work

On TANK (AArch64 Debian Trixie Pi 4), a **fresh clone of the published
`arm64-transmitter` branch at `29c5790`** compiled the updated GUI and backend
natively, using TANK's existing wiringPi, LimeSuite, FastCGI, and libdvbmod
build dependencies. This was a clean-checkout build, **not a fresh OS install**.
A synthetic SRT source in `--dry-run`
confirmed no backend before video, backend start after valid TS, and stop
after both source disconnect and an open-but-stalled sender. TANK has no
DATV-Express board, touchscreen, or `/dev/fb0`; its rover service remained
active. Thus the physical touchscreen, built-in `/touchscreen/` Web Control,
USB firmware/transfer, PTT/RF off timing, decoded receive, and 720p/1080p
live encoding are **not yet verified**. Use a dummy load or attenuated
receiver for the first board test. The stock Web Control mirrors an 800×480
framebuffer; selecting Browser display alone does not create `/dev/fb0` on
TANK. A separate Portsdown Pi with its screen/HDMI framebuffer is needed for
physical display testing.
