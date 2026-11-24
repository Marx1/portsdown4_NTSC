#!/usr/bin/env python3
"""Fail-closed UDP/SRT IPTS or SRT→DVB-S input for DATV-Express.

Only live, FFmpeg-parsed video TS can start a board. On loss, unkey at once,
show the preview card, and re-arm for the next live input. Other legacy IPTS
RF outputs deliberately fail closed instead of reaching a.sh's pre-key path.
"""

import argparse
import fcntl
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import threading
import time

from express_capture_tx import S_FEC, dvbs_server, ptt_receive
from ipts_preview_return import start_preview
from srt_interlocked_tx import FEC as S2_FEC, config, release_legacy_express, stop_child, write_packet

PACKET = 188
STOP = False


def request_stop(_signum, _frame):
    global STOP
    STOP = True


def input_command(cfg, muxrate, pmt_pid, video_pid, input_port=None):
    srt_dvbs = cfg.get("modeinput") == "SRT"
    port = int(input_port if input_port is not None else cfg.get(
        "srtinport" if srt_dvbs else "udpinport", "9000" if srt_dvbs else "10000"))
    if not 1024 <= port <= 65535:
        raise ValueError("invalid TS input port")
    transport = "srt" if srt_dvbs else cfg.get("iptransport", "udp")
    if transport == "srt":
        url = f"srt://0.0.0.0:{port}?mode=listener&transtype=live&latency=200000"
    elif transport == "udp":
        # Keep the UDP socket open while armed, even after hours of silence.
        # A read timeout would close/rebind the port repeatedly and could miss
        # a sender's first PAT/PMT or keyframe. Once TX is active, the video
        # watchdog below stops the encoder/backend on a two-second stall.
        url = f"udp://0.0.0.0:{port}?fifo_size=1000000&overrun_nonfatal=1"
    else:
        raise ValueError("IP TS transport must be udp or srt")
    # Probing incoming MPEG-TS is important: -map 0:v:0 fails when no video
    # stream is found. Source=SRT DVB-S converts any supported source codec
    # to a bounded MPEG-2/MP2 480p profile; IPTS input remains stream-copy.
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostats", "-nostdin",
               "-fflags", "+genpts", "-probesize", "1000000", "-analyzeduration", "1000000",
               "-i", url, "-map", "0:v:0", "-map", "0:a:0?"]
    if srt_dvbs:
        video_rate = (muxrate - 128000 - 40000) * 85 // 100 // 1000 * 1000
        if video_rate < 100000:
            raise ValueError("symbol rate/FEC leaves insufficient MPEG-2 video bitrate")
        # Letterbox/pillarbox in square pixels first. Scaling directly into
        # 720x480 before setting 32:27 SAR would distort a 16:9 input.
        command += ["-vf", "fps=24000/1001,scale=854:480:force_original_aspect_ratio=decrease,"
                    "pad=854:480:(ow-iw)/2:(oh-ih)/2,scale=720:480,setsar=32/27,format=yuv420p",
                    "-c:v", "mpeg2video", "-bf", "0", "-g", "24", "-b:v", str(video_rate),
                    "-maxrate:v", str(video_rate + 100000),
                    "-bufsize:v", str((video_rate + 100000) // 2),
                    "-c:a", "mp2", "-b:a", "128000", "-ac", "2", "-ar", "48000"]
    else:
        command += ["-c", "copy"]
    command += [
               "-mpegts_pmt_start_pid", str(pmt_pid), "-streamid", f"0:{video_pid}",
               "-muxrate", str(muxrate), "-muxdelay", "0", "-muxpreload", "0",
               "-f", "mpegts", "pipe:1"]
    return command, transport, port


def payload_start(packet):
    return bool(packet[1] & 0x40 and packet[3] & 0x10)


def main():
    global STOP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/home/pi/rpidatv/scripts/portsdown_config.txt"))
    parser.add_argument("--backend", type=Path, default=Path("/home/pi/rpidatv/src/express_s2/express_s2"))
    parser.add_argument("--input-port", type=int, help="override SRT/UDP listener port for a test")
    parser.add_argument("--pid-file", type=Path, default=Path("/tmp/portsdown-srt-tx.pid"))
    parser.add_argument("--preview-bind", default="0.0.0.0")
    parser.add_argument("--preview-port", type=int, default=9015)
    parser.add_argument("--preview-udp-port", type=int, default=9016)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        cfg = config(args.config)
        if cfg.get("modeinput") not in ("IPTSIN", "IPTSIN264", "IPTSIN265", "SRT"):
            raise ValueError("select IPTS input or SRT source")
        if cfg.get("modeoutput") not in ("DATVEXPRESS", "DATVEXPRESS_S2"):
            raise ValueError("IPTS RF is currently supported only on DATV-Express; other outputs are blocked")
        modulation = cfg.get("modulation")
        if modulation not in ("DVB-S", "S2QPSK") or (cfg["modeoutput"] == "DATVEXPRESS_S2" and modulation != "S2QPSK"):
            raise ValueError("select Express DVB-S or experimental S2 QPSK")
        if cfg["modeinput"] == "SRT" and modulation != "DVB-S":
            raise ValueError("Source SRT with S2 QPSK uses srt_interlocked_tx.py")
        s2 = modulation == "S2QPSK"
        fec = (S2_FEC if s2 else S_FEC)[cfg["fec"]]
        symbol_rate = int(cfg["symbolrate"]) * 1000
        frequency = round(float(cfg["freqoutput"]) * 1000000)
        pmt_pid = int(cfg.get("pidpmt", "4095"))
        video_pid = int(cfg.get("pidvideo", "256"))
        if not 100000 <= symbol_rate <= 10000000 or not 100000000 <= frequency <= 3000000000:
            raise ValueError("invalid symbol rate or RF frequency")
        if not 32 <= pmt_pid <= 8189 or not 32 <= video_pid <= 8189 or pmt_pid == video_pid:
            raise ValueError("invalid/overlapping TS PIDs")
        if s2:
            if not args.backend.is_file() or not os.access(args.backend, os.X_OK):
                raise ValueError("DVB-S2 backend is missing")
            capacity = int(subprocess.check_output([str(args.backend), "--rate-only", "--symbol-rate",
                         str(symbol_rate), "--fec", fec], text=True).strip())
        else:
            capacity = symbol_rate * 2 * 188 * fec[0] // (204 * fec[1])
        muxrate = capacity * 90 // 100 // 1000 * 1000
        if muxrate < 200000:
            raise ValueError("symbol rate/FEC leaves insufficient TS capacity")
        command, transport, port = input_command(cfg, muxrate, pmt_pid, video_pid, args.input_port)
        for value in (args.preview_port, args.preview_udp_port):
            if not 1024 <= value <= 65535 or value == port:
                raise ValueError("invalid or conflicting preview port")
    except (KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.error(f"invalid IPTS TX configuration: {exc}")

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    with args.pid_file.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("another interlocked Express TX is armed")
        lock.seek(0)
        lock.truncate()
        lock.write(f"{os.getpid()}\n")
        lock.flush()

        live = threading.Event()
        server = None
        if not args.no_preview:
            try:
                server = start_preview(args.preview_bind, args.preview_port, args.preview_udp_port, live)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                print(f"OBS return: http://<this-Pi>:{args.preview_port}/return.ts", flush=True)
            except OSError as exc:
                print(f"IPTS preview unavailable: {exc}", file=sys.stderr, flush=True)
        preview = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        output = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if not s2 and not args.dry_run else None
        try:
            if not args.dry_run:
                if s2:
                    release_legacy_express()
                else:
                    dvbs_server(cfg, frequency, symbol_rate, fec)  # RX/carrier off
            while not STOP:
                encoder = transmitter = None
                keyed = False
                try:
                    print(f"Armed on {transport.upper()} port {port}; RF off until valid live video TS", flush=True)
                    with open("/tmp/portsdown-ipts-ffmpeg.log", "a") as log:
                        encoder = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log)
                        os.set_blocking(encoder.stdout.fileno(), False)
                        pending = bytearray()
                        preroll = []
                        pat = pmt = False
                        video_packets = video_starts = 0
                        first_video = last_video = time.monotonic()
                        udp_data = bytearray()
                        udp_data_preview = bytearray()
                        while not STOP:
                            ready, _, _ = select.select([encoder.stdout], [], [], 0.2)
                            if ready:
                                chunk = os.read(encoder.stdout.fileno(), 1316 * 32)
                                if not chunk:
                                    break
                                pending.extend(chunk)
                            elif encoder.poll() is not None:
                                break
                            while len(pending) >= PACKET and not STOP:
                                packet = bytes(pending[:PACKET])
                                del pending[:PACKET]
                                if packet[0] != 0x47:
                                    raise RuntimeError("invalid TS sync")
                                pid = ((packet[1] & 0x1f) << 8) | packet[2]
                                pat |= pid == 0 and payload_start(packet)
                                pmt |= pid == pmt_pid and payload_start(packet)
                                if pid == video_pid and packet[3] & 0x10:
                                    if video_packets == 0:
                                        first_video = time.monotonic()
                                    video_packets += 1
                                    last_video = time.monotonic()
                                    video_starts += payload_start(packet)
                                if not keyed:
                                    preroll.append(packet)
                                    if len(preroll) > 4000:
                                        preroll.pop(0)
                                    if (pat and pmt and video_packets >= 30 and video_starts >= 3 and
                                            len(preroll) >= 500 and last_video - first_video >= 0.4):
                                        if s2:
                                            backend = [str(args.backend), "--input", "-", "--symbol-rate",
                                                       str(symbol_rate), "--fec", fec]
                                            if not args.dry_run:
                                                backend += ["--tx", "--frequency", str(frequency)]
                                            transmitter = subprocess.Popen(backend, stdin=subprocess.PIPE,
                                                                           cwd=str(args.backend.parent.parent / "dvb_t_stack"))
                                            os.set_blocking(transmitter.stdin.fileno(), False)
                                        elif not args.dry_run:
                                            with open("/tmp/expctrl", "a") as control:
                                                control.write("set ptt tx\n")
                                        keyed = True
                                        live.set()
                                        print("Valid IPTS video; Express TX started" + (" (dry run)" if args.dry_run else ""), flush=True)
                                        for buffered in preroll:
                                            if s2 and not write_packet(transmitter, buffered):
                                                raise RuntimeError("DVB-S2 backend input stalled")
                                            if output:
                                                udp_data.extend(buffered)
                                                if len(udp_data) >= 1316:
                                                    output.sendto(bytes(udp_data[:1316]), ("127.0.0.1", 1314))
                                                    del udp_data[:1316]
                                        preroll.clear()
                                else:
                                    if s2 and not write_packet(transmitter, packet):
                                        raise RuntimeError("DVB-S2 backend input stalled")
                                    if output:
                                        udp_data.extend(packet)
                                        if len(udp_data) >= 1316:
                                            output.sendto(bytes(udp_data[:1316]), ("127.0.0.1", 1314))
                                            del udp_data[:1316]
                                    udp_data_preview.extend(packet)
                                    if len(udp_data_preview) >= 1316:
                                        preview.sendto(bytes(udp_data_preview[:1316]), ("127.0.0.1", args.preview_udp_port))
                                        del udp_data_preview[:1316]
                            if keyed and time.monotonic() - last_video >= 2:
                                print("IPTS video lost; stopping RF", flush=True)
                                break
                            if transmitter and transmitter.poll() is not None:
                                raise RuntimeError("DVB-S2 backend exited")
                except (OSError, RuntimeError) as exc:
                    print(f"IPTS TX error: {exc}", file=sys.stderr, flush=True)
                finally:
                    # The S2 backend is stopped before reconnect; DVB-S PTT
                    # receives an explicit off command even on error/loss.
                    if not s2 and not args.dry_run:
                        try:
                            ptt_receive()
                        except OSError as exc:
                            print(f"Cannot release DVB-S PTT: {exc}; closing Express server",
                                  file=sys.stderr, flush=True)
                            try:
                                subprocess.run(["sudo", "-n", "killall", "express_server"],
                                               check=False, timeout=5)
                            except (OSError, subprocess.SubprocessError) as close_exc:
                                print(f"Cannot close Express server: {close_exc}",
                                      file=sys.stderr, flush=True)
                            STOP = True
                    stop_child(transmitter)
                    live.clear()
                    stop_child(encoder)
                    if keyed:
                        print("IPTS RF stopped; waiting for new live input", flush=True)
                if not STOP:
                    time.sleep(0.5)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f"IPTS TX setup error: {exc}", file=sys.stderr, flush=True)
            return 1
        finally:
            live.clear()
            if not s2 and not args.dry_run:
                try:
                    ptt_receive()
                except OSError:
                    pass
            preview.close()
            if output:
                output.close()
            if server:
                server.stopping = True
                server.shutdown()
                server.server_close()
            lock.seek(0)
            lock.truncate()
            print("IPTS interlock stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
