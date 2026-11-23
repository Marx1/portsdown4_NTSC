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
The GUI's legacy **Encoding → IPTS in** consumes raw UDP TS. To feed it
through the manual bridge, set the receiving Pi's `udpinport=10001` and
`iptransport=udp`; keep the SRT listener on network port 10000. This is a
transport handoff, **not** a verified or loss-interlocked RF path: legacy
IPTS-in-to-transmitter code can key RF before valid TS arrives. Do not use
that legacy path for unattended RF. The separate **Source: SRT → Express S2**
supervisor has a valid-video TX gate, but it transcodes/rate-shapes and is
not a transparent IPTS input.

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
remain unverified. There is no fresh 64-bit Trixie Portsdown installation yet.
Shell syntax and `git diff --check` pass. The changed GUI could not be rebuilt
on the development host because FFTW and FastCGI development headers are
missing; no new TANK native build is claimed for this change.
