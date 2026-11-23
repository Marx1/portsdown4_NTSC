#!/usr/bin/env python3
"""Arm SRT DVB-S2 TX; start the Express backend only for live, valid video TS.

No test card or saved TS is ever sent.  --dry-run exercises the interlock
without opening a DATV-Express board or controlling PTT.
"""

import argparse
import fcntl
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time


PACKET = 188
VIDEO_PID = 4096
PMT_PID = 4095
FEC = {"14": "1/4", "13": "1/3", "12": "1/2", "35": "3/5",
       "23": "2/3", "34": "3/4", "56": "5/6", "89": "8/9", "91": "9/10"}
STOP = False


def request_stop(_signum, _frame):
    global STOP
    STOP = True


def config(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def stop_child(child):
    if child is None:
        return
    if child.poll() is None:
        child.terminate()
    if child.stdin:
        try:
            child.stdin.close()
        except OSError:
            pass
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        # Never leave an orphaned encoder/backend after the supervisor exits.
        # A forced USB-process close is not proof of a safe RF state; hardware
        # testing still has to verify what the board does in this failure case.
        print(f"Child {child.pid} ignored SIGTERM; forcing exit", file=sys.stderr, flush=True)
        child.kill()
        child.wait()


def release_legacy_express():
    """The DVB-S server and raw-16 DVB-S2 backend cannot own USB together."""
    probe = subprocess.run(["pgrep", "-x", "express_server"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if probe.returncode == 1:
        return
    if probe.returncode != 0:
        raise RuntimeError("cannot check legacy DATV-Express server")
    with open("/tmp/expctrl", "a") as control:
        control.write("set ptt rx\nset car off\n")
    subprocess.run(["sudo", "-n", "killall", "express_server"],
                   check=True, timeout=5, stdout=subprocess.DEVNULL)
    for _ in range(30):
        if subprocess.run(["pgrep", "-x", "express_server"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=False).returncode == 1:
            return
        time.sleep(0.1)
    raise RuntimeError("legacy DATV-Express server still owns USB")


def write_packet(child, packet):
    sent = 0
    deadline = time.monotonic() + 2
    while sent < PACKET and not STOP and child.poll() is None:
        if time.monotonic() >= deadline:
            return False
        _, writable, _ = select.select([], [child.stdin], [], 0.2)
        if writable:
            try:
                sent += os.write(child.stdin.fileno(), packet[sent:])
            except (BrokenPipeError, BlockingIOError, OSError):
                return False
    return sent == PACKET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/home/pi/rpidatv/scripts/portsdown_config.txt"))
    parser.add_argument("--backend", type=Path, default=Path("/home/pi/rpidatv/src/express_s2/express_s2"))
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pid-file", type=Path, default=Path("/tmp/portsdown-srt-tx.pid"))
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("invalid SRT port")
    try:
        cfg = config(args.config)
        if (cfg.get("modeinput") != "SRT" or
                cfg.get("modeoutput") not in ("DATVEXPRESS", "DATVEXPRESS_S2") or
                cfg.get("modulation") != "S2QPSK"):
            parser.error("SRT TX requires Source SRT, DATV Express, and S2 QPSK")
        fec = FEC[cfg["fec"]]
        symbol_rate = int(cfg["symbolrate"]) * 1000
        frequency = round(float(cfg["freqoutput"]) * 1000000)
        if not 100000 <= symbol_rate <= 10000000 or not 100000000 <= frequency <= 3000000000:
            parser.error("invalid symbol rate or RF frequency")
        resolution = {"720p": (1280, 720), "1080p": (1920, 1080)}.get(cfg.get("format"), (854, 480))
    except (OSError, KeyError, ValueError) as exc:
        parser.error(f"invalid Portsdown configuration: {exc}")
    if not args.backend.is_file() or not os.access(args.backend, os.X_OK):
        parser.error(f"DVB-S2 backend missing or not executable: {args.backend}")
    try:
        capacity = int(subprocess.check_output([str(args.backend), "--rate-only", "--symbol-rate", str(symbol_rate), "--fec", fec], text=True).strip())
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.error(f"cannot calculate DVB-S2 capacity: {exc}")
    muxrate = capacity * 95 // 100 // 1000 * 1000
    video_rate = (muxrate - 48000 - 40000) * 55 // 100 // 1000 * 1000
    if video_rate < 100000:
        parser.error("FEC/symbol rate leaves insufficient video bitrate")

    if not args.dry_run:
        try:
            release_legacy_express()
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            parser.error(f"cannot release legacy DATV-Express board: {exc}")

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    lock = args.pid_file.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("SRT TX is already armed")
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()) + "\n")
    lock.flush()

    width, height = resolution
    fps = "15" if height == 1080 or (height == 720 and muxrate < 1200000) else "24000/1001"
    vf = (f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
    srt = f"srt://0.0.0.0:{args.port}?mode=listener&latency=200000"
    ffmpeg = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostats", "-nostdin",
              "-i", srt, "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf,
              "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
              "-profile:v", "baseline", "-bf", "0", "-g", "30" if fps == "15" else "48",
              "-b:v", str(video_rate), "-maxrate:v", str(video_rate),
              "-bufsize:v", str(video_rate // 2), "-c:a", "aac", "-b:a", "48000",
              "-ac", "1", "-ar", "48000", "-mpegts_pmt_start_pid", str(PMT_PID),
              "-streamid", f"0:{VIDEO_PID}", "-muxrate", str(muxrate), "-f", "mpegts", "pipe:1"]
    backend = [str(args.backend), "--input", "-", "--symbol-rate", str(symbol_rate), "--fec", fec]
    if not args.dry_run:
        backend += ["--tx", "--frequency", str(frequency)]
    encoder = None
    transmitter = None
    # FFmpeg diagnostics go to the log; never let stderr fill a pipe.
    with open("/tmp/portsdown-srt-ffmpeg.log", "a") as ffmpeg_log:
        try:
            encoder = subprocess.Popen(ffmpeg, stdout=subprocess.PIPE, stderr=ffmpeg_log)
            os.set_blocking(encoder.stdout.fileno(), False)
            pending = bytearray()
            preroll = []
            have_pat = have_pmt = False
            video_packets = 0
            last_video = time.monotonic()
            print(f"Armed on SRT port {args.port}; RF off until live video TS", flush=True)
            while not STOP:
                if encoder.poll() is not None:
                    print("SRT/FFmpeg stopped; stopping TX", flush=True)
                    break
                readable, _, _ = select.select([encoder.stdout], [], [], 0.2)
                if readable:
                    try:
                        chunk = os.read(encoder.stdout.fileno(), 1316 * 32)
                    except BlockingIOError:
                        chunk = b""
                    if not chunk:
                        print("SRT TS ended; stopping TX", flush=True)
                        break
                    pending.extend(chunk)
                while len(pending) >= PACKET and not STOP:
                    packet = bytes(pending[:PACKET])
                    del pending[:PACKET]
                    if packet[0] != 0x47:
                        print("Invalid TS sync; stopping TX", file=sys.stderr, flush=True)
                        return 1
                    pid = ((packet[1] & 0x1f) << 8) | packet[2]
                    payload = bool(packet[3] & 0x10)
                    if pid == 0:
                        have_pat = True
                    elif pid == PMT_PID:
                        have_pmt = True
                    elif pid == VIDEO_PID and payload:
                        video_packets += 1
                        last_video = time.monotonic()
                    if transmitter is None:
                        preroll.append(packet)
                        if len(preroll) > 2000:
                            preroll.pop(0)
                        if have_pat and have_pmt and video_packets >= 30 and len(preroll) >= 500:
                            # The backend is created only after live SRT yielded
                            # a PAT, PMT and sustained video payload.
                            if time.monotonic() - last_video > 1:
                                continue
                            transmitter = subprocess.Popen(backend, stdin=subprocess.PIPE,
                                                           cwd=str(args.backend.parent.parent / "dvb_t_stack"))
                            os.set_blocking(transmitter.stdin.fileno(), False)
                            print("Valid live SRT TS; DVB-S2 backend started" + (" (dry run)" if args.dry_run else ""), flush=True)
                            for buffered in preroll:
                                if not write_packet(transmitter, buffered):
                                    raise RuntimeError("DVB-S2 backend input stalled")
                            preroll.clear()
                    elif not write_packet(transmitter, packet):
                        raise RuntimeError("DVB-S2 backend input stalled")
                if transmitter and time.monotonic() - last_video >= 2:
                    print("Live video TS stalled; stopping TX", flush=True)
                    break
                if transmitter and transmitter.poll() is not None:
                    raise RuntimeError("DVB-S2 backend exited")
        except (OSError, RuntimeError) as exc:
            print(f"SRT TX error: {exc}", file=sys.stderr, flush=True)
            return 1
        finally:
            # Stop the RF backend first, then the SRT encoder.  No fallback.
            stop_child(transmitter)
            stop_child(encoder)
            lock.seek(0)
            lock.truncate()
            lock.close()
            print("SRT TX stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
