# Streamer and IP Output: two different network jobs

The touchscreen now calls the existing `IP` output **IP Output**. It remains
separate from **BATC Stream** (`STREAMER`).

| Output | Transport | Intended destination |
| --- | --- | --- |
| BATC Stream / Streamer | RTMP/FLV to `streamurl/streamkey` | BATC or another RTMP server. Its legacy capture/encoder code has **not** been ported/verified on Trixie. |
| IP Output, UDP | MPEG-TS over UDP to `udpoutaddr:udpoutport` | Existing direct TS/UDP receiver; default behavior. |
| IP Output, SRT | Live MPEG-TS video/audio via SRT caller to `udpoutaddr:udpoutport` | Another Pi's SRT bridge, which delivers TS on localhost UDP for IPTS Monitor or a later IPTS input. |

SRT is a **transport option for IP TS**, not an RTMP replacement or a
modulation mode. The bridge uses FFmpeg stream-copy/remux, like the existing
OBS/ATEM SRT ingest work. It does not re-encode, shape the TS to a DVB
symbol/FEC capacity, open a board, key RF, or replay saved TS. When source
packets stop, forwarded video stops; a lost SRT session is retried. The
separate [OBS→TANK work](mse88-obs-srt-to-tank.md) performs rate-shaped TS
creation; its 480p/720p/1080p offline results do not prove this new
Portsdown-to-Portsdown GUI route on two physical Pis.

## Two-system SRT confidence link

Both systems need FFmpeg with `srt` listed by `ffmpeg -protocols`, plus the
changed scripts. Use distinct ports for the network SRT listener and local
UDP delivery. The defaults below use **network UDP 10000 for SRT** and
**localhost UDP 10001 for MPEG-TS**. SRT runs over UDP, but it is not raw
UDP MPEG-TS; both ends must choose the same transport.

1. On the **receiving Pi**, select **System → TS IP Config → IP TS: SRT** and
   set **TS In IP Port = 10000**. Select the **IPTS Monitor**. Its `av5.sh`
   starts `ipts_srt_bridge.sh --receive`, listens for SRT on UDP 10000, and
   gives VLC live TS on `127.0.0.1:10001`. It stops the bridge when the
   monitor closes. Network/firewall rules must allow UDP 10000 to this Pi.
2. On the **sending Pi**, select the desired supported video source, choose
   **Output Device → IP Output**, then **System → TS IP Config → IP TS: SRT**.
   Set **TS Out IP Address** to the receiver's IPv4 address and **TS Out IP
   Port = 10000**. Press TX. The encoder sends TS to `127.0.0.1:10001`, and
   the bridge calls the receiver by SRT. Press Stop to terminate both encoder
   and bridge. `iptransport=udp` switches back to the original direct UDP
   output without touching Streamer presets.

For a manual receiving bridge without IPTS Monitor, run:

```sh
scripts/ipts_srt_bridge.sh --receive --srt-port 10000 \
  --udp-port 10001 --pid-file /tmp/manual-ipts-srt.pid
```

Then point a local TS player or ingest process at `udp://127.0.0.1:10001`.
Stop that bridge with `scripts/ipts_srt_stop.sh /tmp/manual-ipts-srt.pid`.
The GUI's **Encoding → IPTS in** can now receive raw UDP TS or listen for SRT
directly. For RF input, select **TS IP Config → IP TS: UDP/SRT** and set
**TS In IP Port**. Do **not** start the separate SRT monitor bridge on that
same port. A manual bridge can still translate SRT to local UDP: set
`udpinport=10001` and `iptransport=udp`, leaving the bridge listener on
network port 10000.

### TANK SRT MPEG-TS destinations

| Selection | SRT listener | TS treatment | Output |
| --- | --- | --- | --- |
| **Source → SRT**, **Express**, **DVB-S** | `srtinport` (default **9000**) | Transcode video/audio to rate-shaped 720×480 MPEG-2/MP2 TS | Interlocked Express DVB-S; preview on HTTP 9015 |
| **Source → SRT**, **Express** or **Express S2**, **S2 QPSK** | `srtinport` (default **9000**) | Transcode to rate-shaped H.264/AAC TS | Interlocked experimental Express DVB-S2 |
| **Encoding → IPTS in**, **IP TS: SRT**, **Express DVB-S/S2** | `udpinport` (default **10000**) | Stream-copy/remux MPEG-TS, no video transcoding | Interlocked Express DVB-S or experimental S2; preview on HTTP 9015 |
| **IPTS Monitor**, **IP TS: SRT** | `udpinport` (default **10000**) | SRT-to-local-UDP bridge | VLC monitor, **no RF** |
| Bounded `srt_datv_ts_listener.py` | Usually **9000** | Make a validated DVB-S or S2 TS file | Offline preparation, **no RF** |

The sender must use SRT **MPEG-TS**, not raw UDP packets or RTMP/FLV. Start
only one listener on any given port; for example, stop the bounded OBS/TANK
preview cycle before arming Source=SRT on port 9000. These are alternative
routes, not simultaneous consumers of a single SRT call.

### Interlocked IPTS input to Express RF (experimental)

**Encoding → IPTS in / IPTS in H264 / IPTS in H265** now bypasses the old
`a.sh` IPTS case. That case used to start PTT/modulators before TS arrived.
The new `ipts_interlocked_tx.py` waits for a live FFmpeg-probed video stream,
fresh PAT/PMT, at least 30 video packets and three video PES starts before
it starts **DATV-Express DVB-S** or the experimental **Express DVB-S2 QPSK**
backend. SRT is listened to directly on `udpinport`; raw UDP TS is also
accepted there. Pressing TX with no source **arms a persistent listener but
does not key RF**. In particular, the UDP socket stays bound while silent;
the sender can begin later without aiming at a narrow reconnect window.
When video packets cease for two seconds, or the sender
disconnects, it releases DVB-S PTT or stops the DVB-S2 backend. It remains
armed with RF off and waits for a *new live* source; pressing Stop ends the
supervisor. It never sends the preview card or a saved TS to RF.

Other IPTS-to-RF outputs (Pi, Lime, Pluto, Muntjac, etc.) now **fail closed**
instead of falling into the pre-key legacy path. They need individual
interlocked ports before they can be used with IPTS input again. IPTS input
paired with IP Output/Streamer is also not a supported TX combination yet;
the separate IPTS Monitor and IP Output sender remain available. The current
IPTS-in path remuxes/copies video and optional audio, requesting a TS mux rate at
90% of the selected symbol-rate/FEC capacity; it neither validates input
bitrate nor transcodes oversized inputs. Supply a
source bitrate below that capacity and a regular keyframe with repeated
codec headers (OBS/FFmpeg: around one-second GOP). A PAT/PMT/video-packet
gate does not prove all video frames are decodable or RF quality.

While IPTS TX is armed, add `http://<Portsdown-Pi>:9015/return.ts` as an OBS
Media Source (local file unchecked). It serves 426×240 H.264/AAC TS over
HTTP. With no validated input, it shows SMPTE bars with centered black
**NO IP INPUT** text; it switches to live video after the gate, and back to
the card after loss. The preview receives only the supervisor's live TS
copy on localhost UDP 9016. It neither keys RF nor loops a recording. Port
9015 is separate from TANK's existing OBS SRT return on port 9013. This
preview exists while IPTS TX is armed; pressing Stop closes the HTTP server.

`iptslocalport=10001` can be changed in `portsdown_config.txt` if localhost
UDP 10001 is occupied. The SRT bridge's receive and transmit processes use
different PID files. Do not run this bridge on port 9000 while the OBS/TANK
SRT listener or Express S2 supervisor owns that port.

## Current verification boundary

A bounded same-host test sent two bursts of synthetic H.264/AAC MPEG-TS
through sender and receiver bridges on separate loopback ports. The receiver
produced aligned 188-byte TS packets; `ffprobe` found 320×240 H.264 and AAC
audio after both bursts. The stop helper cleared each bridge's PID file.
That verifies the transport mechanism only. Physical
Portsdown menus, two-Pi networking, camera/HDMI/audio capture, Streamer RTMP
on Trixie, IPTS monitor playback, TS rate suitability, and downstream RF
remain unverified. The new IPTS RF gate was tested in DVB-S dry-run with
UDP TS: no input kept RF off, live synthetic H.264 TS passed the gate, and
stopping input dropped the gate. An SRT dry-run with a fake DVB-S2 backend
also started only after video and stopped the backend on sender disconnect.
The automated offline test leaves each listener idle for five seconds, then
sends two separate bursts; both UDP and SRT detected both starts and stopped
the dry-run backend after each loss. Source=SRT → Express DVB-S also passed a
bounded H.264/AAC SRT input → MPEG-2/MP2 720×480 TS dry run, including a
second source burst after loss. Run the automated checks with
`python3 -B tests/test_ipts_interlock_offline.py -v`.
The preview card rendered correctly; a continuous HTTP TS capture decoded
card → live → card, without changing the OBS URL. These are **software-only**
checks: USB, PTT off timing, RF, GUI runtime, two-Pi network, and receiver
decode still need hardware testing. There is no fresh 64-bit Trixie Portsdown
installation yet.
Shell syntax and `git diff --check` pass. The changed GUI could not be rebuilt
on the development host because FFTW and FastCGI development headers are
missing; no new TANK native build is claimed for this change.
