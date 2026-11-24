#!/usr/bin/env python3
"""Interlocked local-video capture for DATV-Express DVB-S or DVB-S2 QPSK.

Only the explicitly supported live sources below are accepted. --dry-run never
opens a board or asserts PTT. A selected test-card image is the sole looping
source; a lost live camera is never replaced by a saved recording.
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
import time

from srt_interlocked_tx import FEC as S2_FEC, config, release_legacy_express, stop_child, write_packet

STOP = False
PACKET = 188
S_FEC = {"1": (1, 2), "2": (2, 3), "3": (3, 4), "5": (5, 6), "7": (7, 8)}


def request_stop(_signum, _frame):
    global STOP
    STOP = True


def capture_command(cfg, helper, muxrate, video_rate):
    mode = cfg.get("modeinput", "")
    fmt = cfg.get("format", "4:3")
    size = {"720p": "1280x720", "1080p": "1920x1080", "16:9": "854x480"}.get(fmt, "720x480")
    codec = "mpeg2" if "MPEG-2" in mode or cfg.get("encoding") == "MPEG-2" else "h264"
    args = [str(helper), "--codec", codec, "--output", "pipe:1", "--size", size,
            "--fps", "30000/1001", "--video-bitrate", str(video_rate),
            "--muxrate", str(muxrate), "--pmt-pid", cfg.get("pidpmt", "4095"),
            "--video-pid", cfg.get("pidvideo", "256"),
            "--audio-pid", cfg.get("pidaudio", "257"),
            "--service-id", cfg.get("serviceid", "1"),
            "--service-name", cfg.get("call", "Portsdown"),
            "--video-encoder", cfg.get("h264encoder", "auto")]

    if mode.startswith("CAM"):
        args += ["--source", "rpicam"]
        if cfg.get("picam") not in (None, "normal"):
            args += ["--rotation", "180"]
    elif mode.startswith("ANALOG"):
        device = cfg.get("analogcamname", "")
        if not device.startswith("/dev/video"):
            raise ValueError("set analogcamname to the NTSC V4L2 device")
        args += ["--source", device, "--input-format", "yuyv422",
                 "--capture-size", "720x480", "--capture-rate", "30000/1001",
                 "--deinterlace"]
    elif mode.startswith(("WEBCAM", "C920")):
        device = cfg.get("expresswebcamdevice", "")
        if not device.startswith("/dev/video"):
            raise ValueError("set expresswebcamdevice to the webcam V4L2 device")
        args += ["--source", device]
    elif mode == "HDMI":
        device = cfg.get("expresshdmidevice", "")
        if not device.startswith("/dev/video"):
            raise ValueError("set expresshdmidevice to the HDMI capture V4L2 device")
        args += ["--source", device]
    elif mode.startswith("CARD") or mode == "PATERNAUDIO":
        default_card = "tcf1080.jpg" if fmt == "1080p" else "tcfw.jpg" if fmt in ("16:9", "720p") else "tcf.jpg"
        card = cfg.get("expresstestcard", str(helper.parent / "images" / default_card))
        args += ["--source", f"image:{card}", "--loop-image"]
    else:
        raise ValueError(f"Express Trixie capture source {mode!r} is not ported")

    audio = cfg.get("expressaudiodevice", "")
    if audio:
        args += ["--audio-device", audio, "--audio-bitrate", "48000"]
    return args


def dvbs_server(cfg, frequency, symbol_rate, fec):
    server_dir = Path("/home/pi/express_server")
    server = server_dir / "express_server"
    if not server.is_file():
        raise RuntimeError("legacy DATV-Express DVB-S server is not installed")
    running = subprocess.run(["pgrep", "-x", "express_server"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             check=False).returncode == 0
    if not running:
        subprocess.Popen(["sudo", "-n", str(server)], cwd=server_dir,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(50):
            if subprocess.run(["pgrep", "-x", "express_server"],
                              stdout=subprocess.DEVNULL, check=False).returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("DATV-Express DVB-S server did not start")
    with open("/tmp/expctrl", "a") as control:
        control.write("set ptt rx\nset car off\n")
        control.write(f"set freq {frequency}\nset fec {fec[0]}/{fec[1]}\n")
        control.write(f"set srate {symbol_rate}\nset level {cfg.get('explevel', '30')}\n")


def ptt_receive():
    with open("/tmp/expctrl", "a") as control:
        control.write("set ptt rx\nset car off\n")


def prepare_live_capture(cfg, command):
    mode = cfg.get("modeinput", "")
    if mode.startswith("ANALOG"):
        device = cfg["analogcamname"]
        subprocess.run(["v4l2-ctl", "-d", device, "--set-standard=ntsc"],
                       check=True, timeout=5)
        input_number = cfg.get("analogcaminput", "-")
        if input_number != "-":
            subprocess.run(["v4l2-ctl", "-d", device, f"--set-input={int(input_number)}"],
                           check=True, timeout=5)
    elif mode.startswith(("WEBCAM", "C920")):
        formats = subprocess.run(["v4l2-ctl", "-d", cfg["expresswebcamdevice"],
                                  "--list-formats-ext"], check=True, capture_output=True,
                                 text=True, timeout=5).stdout
        command += ["--input-format", "mjpeg" if "'MJPG'" in formats else "yuyv422"]


def stop_capture(child):
    """Stop the shell helper and every member of its camera/FFmpeg pipeline."""
    if child is None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()
    if child.stdout:
        child.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/home/pi/rpidatv/scripts/portsdown_config.txt"))
    parser.add_argument("--helper", type=Path, default=Path("/home/pi/rpidatv/scripts/capture_ts_ffmpeg.sh"))
    parser.add_argument("--backend", type=Path, default=Path("/home/pi/rpidatv/src/express_s2/express_s2"))
    parser.add_argument("--pid-file", type=Path, default=Path("/tmp/portsdown-srt-tx.pid"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        cfg = config(args.config)
        output = cfg.get("modeoutput")
        modulation = cfg.get("modulation")
        if output not in ("DATVEXPRESS", "DATVEXPRESS_S2") or modulation not in ("DVB-S", "S2QPSK"):
            raise ValueError("requires Express output and DVB-S or S2 QPSK")
        if output == "DATVEXPRESS_S2" and modulation != "S2QPSK":
            raise ValueError("Express S2 output requires S2 QPSK")
        s2 = modulation == "S2QPSK"
        fec_code = cfg["fec"]
        fec = S2_FEC[fec_code] if s2 else S_FEC[fec_code]
        symbol_rate = int(cfg["symbolrate"]) * 1000
        frequency = round(float(cfg["freqoutput"]) * 1000000)
        if not 100000 <= symbol_rate <= 10000000 or not 100000000 <= frequency <= 3000000000:
            raise ValueError("invalid symbol rate or RF frequency")
        for key in ("pidpmt", "pidvideo", "pidaudio"):
            pid = int(cfg.get(key, "0"))
            if not 32 <= pid <= 8189:
                raise ValueError(f"invalid {key}")
        if not args.helper.is_file() or not os.access(args.helper, os.X_OK):
            raise ValueError("Trixie FFmpeg capture helper is missing")
        if s2:
            if not args.backend.is_file() or not os.access(args.backend, os.X_OK):
                raise ValueError("DVB-S2 backend is missing")
            capacity = int(subprocess.check_output([str(args.backend), "--rate-only",
                         "--symbol-rate", str(symbol_rate), "--fec", fec], text=True).strip())
        else:
            capacity = symbol_rate * 2 * 188 * fec[0] // (204 * fec[1])
        muxrate = capacity * 95 // 100 // 1000 * 1000
        video_rate = (muxrate - 48000 - 40000) * 65 // 100 // 1000 * 1000
        if video_rate < 100000:
            raise ValueError("FEC/symbol rate leaves insufficient video bitrate")
        command = capture_command(cfg, args.helper, muxrate, video_rate)
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(f"invalid Express capture configuration: {exc}")

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    lock = args.pid_file.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("another Express TX is armed")
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()) + "\n")
    lock.flush()

    encoder = transmitter = None
    udp = None
    udp_data = bytearray()
    keyed = False
    try:
        if not args.dry_run:
            if s2:
                release_legacy_express()
            else:
                dvbs_server(cfg, frequency, symbol_rate, fec)
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        prepare_live_capture(cfg, command)
        with open("/tmp/portsdown-express-capture.log", "a") as capture_log:
            encoder = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=capture_log,
                                       start_new_session=True)
            os.set_blocking(encoder.stdout.fileno(), False)
            pending = bytearray()
            preroll = []
            pat = pmt = False
            video_packets = 0
            video_pid = int(cfg.get("pidvideo", "256"))
            pmt_pid = int(cfg.get("pidpmt", "4095"))
            last_video = time.monotonic()
            print(f"Express {modulation} armed; RF off until live video TS", flush=True)
            while not STOP:
                if encoder.poll() is not None:
                    break
                readable, _, _ = select.select([encoder.stdout], [], [], 0.2)
                if readable:
                    chunk = os.read(encoder.stdout.fileno(), 1316 * 32)
                    if not chunk:
                        break
                    pending.extend(chunk)
                while len(pending) >= PACKET and not STOP:
                    packet = bytes(pending[:PACKET])
                    del pending[:PACKET]
                    if packet[0] != 0x47:
                        raise RuntimeError("invalid TS sync")
                    pid = ((packet[1] & 0x1f) << 8) | packet[2]
                    pat |= pid == 0
                    pmt |= pid == pmt_pid
                    if pid == video_pid and packet[3] & 0x10:
                        video_packets += 1
                        last_video = time.monotonic()
                    if not keyed:
                        preroll.append(packet)
                        if len(preroll) > 2000:
                            preroll.pop(0)
                        if pat and pmt and video_packets >= 30 and len(preroll) >= 500:
                            if s2:
                                backend_cmd = [str(args.backend), "--input", "-", "--symbol-rate",
                                               str(symbol_rate), "--fec", fec]
                                if not args.dry_run:
                                    backend_cmd += ["--tx", "--frequency", str(frequency)]
                                transmitter = subprocess.Popen(backend_cmd, stdin=subprocess.PIPE,
                                                               cwd=str(args.backend.parent.parent / "dvb_t_stack"))
                                os.set_blocking(transmitter.stdin.fileno(), False)
                            elif not args.dry_run:
                                with open("/tmp/expctrl", "a") as control:
                                    control.write("set ptt tx\n")
                            keyed = True
                            print(f"Valid live video; Express {modulation} started" +
                                  (" (dry run)" if args.dry_run else ""), flush=True)
                            for buffered in preroll:
                                if s2 and transmitter:
                                    if not write_packet(transmitter, buffered):
                                        raise RuntimeError("DVB-S2 backend input stalled")
                                elif udp:
                                    udp_data.extend(buffered)
                                    if len(udp_data) >= 1316:
                                        udp.sendto(bytes(udp_data[:1316]), ("127.0.0.1", 1314))
                                        del udp_data[:1316]
                            preroll.clear()
                    elif s2 and transmitter:
                        if not write_packet(transmitter, packet):
                            raise RuntimeError("DVB-S2 backend input stalled")
                    elif udp:
                        udp_data.extend(packet)
                        if len(udp_data) >= 1316:
                            udp.sendto(bytes(udp_data[:1316]), ("127.0.0.1", 1314))
                            del udp_data[:1316]
                if keyed and time.monotonic() - last_video >= 2:
                    raise RuntimeError("live video stalled")
                if transmitter and transmitter.poll() is not None:
                    raise RuntimeError("DVB-S2 backend stopped")
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Express capture TX error: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        if keyed and not s2 and not args.dry_run:
            try:
                ptt_receive()
            except OSError as exc:
                print(f"Cannot release DVB-S PTT: {exc}", file=sys.stderr, flush=True)
        stop_child(transmitter)
        stop_capture(encoder)
        if udp:
            udp.close()
        lock.seek(0)
        lock.truncate()
        lock.close()
        print("Express capture TX stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
