#!/usr/bin/env python3
"""Capture one SRT call, then create a bounded, rate-shaped DATV MPEG-TS file.

This is TS preparation only. It never opens transmitter hardware or keys PTT.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys


DVBS_FEC = {"1/2": (1, 2), "2/3": (2, 3), "3/4": (3, 4),
            "5/6": (5, 6), "7/8": (7, 8)}
DVBS2_FEC = ("1/4", "1/3", "2/5", "1/2", "3/5", "2/3",
             "3/4", "4/5", "5/6", "8/9", "9/10")
S2_BACKEND = Path("/home/leo/portsdown-express-s2-arm64/src/express_s2/express_s2")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("dvbs", "dvbs2"))
    parser.add_argument("--fec", required=True, help="FEC used by the matching modulator")
    parser.add_argument("--resolution", default="480p", choices=("480p", "720p", "1080p"))
    parser.add_argument("--symbol-rate", type=int, help="symbols/s; default 2222000 (S) or 1000000 (S2)")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--startup-grace", type=int, default=300,
                        help="extra seconds allowed for a caller to connect (default: 300)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-file", type=Path,
                        help="transcode an existing capture instead of listening on SRT")
    parser.add_argument("--ingest-file", type=Path,
                        help="where to retain the received source TS (default: OUTPUT.ingest.ts)")
    parser.add_argument("--preview-udp", help="also forward incoming TS to a local UDP live preview")
    parser.add_argument("--preview-end-file", type=Path,
                        help="touch this file when SRT capture ends, before offline validation")
    parser.add_argument("--s2-backend", type=Path, default=S2_BACKEND)
    args = parser.parse_args()

    if args.mode == "dvbs" and args.resolution != "480p":
        parser.error("DVB-S MPEG-2 profile is 480p only")
    allowed = DVBS_FEC if args.mode == "dvbs" else DVBS2_FEC
    if args.fec not in allowed:
        parser.error(f"FEC for {args.mode} must be one of: {', '.join(allowed)}")
    symbol_rate = args.symbol_rate or (2222000 if args.mode == "dvbs" else 1000000)
    if not 100000 <= symbol_rate <= 10000000:
        parser.error("symbol rate must be 100000-10000000 symbols/s")
    if (not 1024 <= args.port <= 65535 or not 1 <= args.duration <= 3600
            or not 0 <= args.startup_grace <= 3600):
        parser.error("port must be 1024-65535, duration 1-3600 s, and startup grace 0-3600 s")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    if not args.output.parent.is_dir():
        parser.error(f"output directory does not exist: {args.output.parent}")
    if args.input_file and args.ingest_file:
        parser.error("--input-file and --ingest-file cannot be combined")
    if args.input_file and (args.preview_udp or args.preview_end_file):
        parser.error("live preview options require an SRT input")
    if args.preview_udp and not args.preview_udp.startswith("udp://127.0.0.1:"):
        parser.error("--preview-udp must target localhost")
    ingest_file = args.input_file or args.ingest_file or args.output.with_name(
        args.output.stem + ".ingest.ts")
    if args.input_file:
        if not ingest_file.is_file():
            parser.error(f"input file not found: {ingest_file}")
    elif ingest_file.exists() or not ingest_file.parent.is_dir():
        parser.error(f"ingest path exists or its directory is missing: {ingest_file}")
    if ingest_file.resolve() == args.output.resolve():
        parser.error("ingest and output paths must differ")

    if args.mode == "dvbs":
        numerator, denominator = DVBS_FEC[args.fec]
        # QPSK, 204-byte Reed-Solomon outer code carrying 188-byte TS packets.
        capacity = symbol_rate * 2 * numerator * 188 // (denominator * 204)
    else:
        try:
            result = subprocess.run(
                [str(args.s2_backend), "--rate-only", "--symbol-rate", str(symbol_rate),
                 "--fec", args.fec], check=True, capture_output=True, text=True)
            capacity = int(result.stdout.strip())
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            parser.error(f"cannot get exact DVB-S2 TS capacity from backend: {exc}")

    # Leave capacity margin; reject files with measured over-capacity rate
    # or FFmpeg-reported PCR timing errors after the bounded capture.
    mux_percent = 95
    muxrate = capacity * mux_percent // 100 // 1000 * 1000
    audio_rate = 128000 if args.mode == "dvbs" else 48000
    video_fraction = 85 if args.mode == "dvbs" else 55
    video_divisor = 100
    video_rate = (muxrate - audio_rate - 40000) * video_fraction // video_divisor // 1000 * 1000
    if video_rate < 100000:
        parser.error("selected FEC/symbol rate leaves insufficient room for video")

    if args.mode == "dvbs":
        # 720x480 with 16:9 display aspect ratio, conventional MPEG-2 SD raster.
        video_filter = "fps=24000/1001,scale=720:480:force_original_aspect_ratio=decrease,pad=720:480:(ow-iw)/2:(oh-ih)/2,setsar=32/27,format=yuv420p"
        video_encoder = ["-c:v", "mpeg2video", "-bf", "0", "-g", "24"]
        # Keep MPEG-2 VBV peaks well below the fixed TS mux rate. The old
        # 120% peaks could outrun it on real OBS scenes (dts < pcr).
        video_maxrate = video_rate + 100000
        audio_encoder = ["-c:a", "mp2", "-b:a", str(audio_rate), "-ac", "2", "-ar", "48000"]
    else:
        width, height = {"480p": (854, 480), "720p": (1280, 720),
                         "1080p": (1920, 1080)}[args.resolution]
        frame_rate = "15" if args.resolution == "1080p" or (args.resolution == "720p" and muxrate < 1200000) else "24000/1001"
        video_filter = (f"fps={frame_rate},scale={width}:{height}:force_original_aspect_ratio=decrease,"
                        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
        video_encoder = ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                         "-profile:v", "baseline", "-bf", "0", "-g",
                         "30" if frame_rate == "15" else "48"]
        video_maxrate = video_rate
        audio_encoder = ["-c:a", "aac", "-b:a", str(audio_rate), "-ac", "1", "-ar", "48000"]

    if not args.input_file:
        url = f"srt://0.0.0.0:{args.port}?mode=listener&latency=200000"
        capture = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostats",
                   "-nostdin", "-n", "-i", url, "-t", str(args.duration),
                   "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-f", "mpegts",
                   str(ingest_file)]
        if args.preview_udp:
            capture += ["-t", str(args.duration), "-map", "0:v:0", "-map", "0:a:0?",
                        "-c", "copy", "-f", "mpegts", args.preview_udp]
        print(f"Listening on SRT port {args.port}; retaining ingest at {ingest_file}", flush=True)
        try:
            received = subprocess.run(capture, capture_output=True, text=True,
                                      timeout=args.duration + args.startup_grace + 30)
        except subprocess.TimeoutExpired:
            print("SRT capture timed out; checking retained partial ingest", file=sys.stderr)
            received = None
        if args.preview_end_file:
            args.preview_end_file.touch()
        if received and received.stderr:
            print(received.stderr, file=sys.stderr, end="")
        if ((received is not None and received.returncode) or not ingest_file.is_file()
                or ingest_file.stat().st_size < 18800):
            print("SRT capture failed or received too little data", file=sys.stderr)
            return 1

    try:
        source_probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(ingest_file)],
            check=True, capture_output=True, text=True)
        streams = json.loads(source_probe.stdout)["streams"]
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Unable to inspect source capture: {exc}", file=sys.stderr)
        return 1
    if not any(stream.get("codec_type") == "video" for stream in streams):
        print("Source capture has no video stream", file=sys.stderr)
        return 1
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)

    command = ["ffmpeg", "-hide_banner", "-loglevel", "info", "-nostats", "-nostdin", "-n",
               "-i", str(ingest_file), "-t", str(args.duration), "-map", "0:v:0"]
    if has_audio:
        command.extend(["-map", "0:a:0"])
    command += [
               "-vf", video_filter, *video_encoder, "-b:v", str(video_rate),
               "-maxrate:v", str(video_maxrate), "-bufsize:v",
               str(video_maxrate // 2)]
    if has_audio:
        command.extend(audio_encoder)
    command += ["-mpegts_pmt_start_pid", "4095", "-streamid", "0:4096",
                "-muxrate", str(muxrate), "-f", "mpegts", str(args.output)]
    print(f"{args.mode.upper()} QPSK {symbol_rate} sym/s FEC {args.fec}: "
          f"capacity={capacity}, TS muxrate={muxrate}, video={video_rate} bit/s; "
          f"output={args.resolution}", flush=True)
    if args.mode == "dvbs2" and args.resolution == "1080p" and video_rate < 1500000:
        print("Warning: 1080p at this bitrate will be low quality; real-time Pi encoding is unverified.",
              file=sys.stderr, flush=True)
    invalid_ts = False
    with subprocess.Popen(command, stderr=subprocess.PIPE, text=True) as process:
        for line in process.stderr:
            print(line, file=sys.stderr, end="", flush=True)
            if "dts < pcr" in line:
                invalid_ts = True
        result = process.wait()
    if result:
        return result
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate,duration,size",
             "-show_entries", "stream=codec_type,codec_name,width,height",
             "-of", "json", str(args.output)],
            check=True, capture_output=True, text=True)
        result_info = json.loads(probe.stdout)
        actual_rate = int(result_info["format"]["bit_rate"])
        actual_duration = float(result_info["format"]["duration"])
        actual_size = int(result_info["format"]["size"])
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Unable to verify TS bitrate: {exc}", file=sys.stderr)
        return 1
    print(f"Measured TS bitrate={actual_rate} bit/s; modulator capacity={capacity} bit/s")
    if actual_rate > capacity:
        print("TS exceeds selected FEC capacity; do not feed it to the modulator.", file=sys.stderr)
        return 1
    if invalid_ts:
        print("FFmpeg reported dts < pcr; TS timing is invalid for this profile.", file=sys.stderr)
        return 1
    expected_codec = "mpeg2video" if args.mode == "dvbs" else "h264"
    video_streams = [stream for stream in result_info["streams"]
                     if stream.get("codec_type") == "video"]
    expected_dimensions = (720, 480) if args.mode == "dvbs" else (width, height)
    if (len(video_streams) != 1 or video_streams[0].get("codec_name") != expected_codec
            or (video_streams[0].get("width"), video_streams[0].get("height")) != expected_dimensions
            or actual_size % 188 != 0 or actual_duration <= 0):
        print("Output TS codec, dimensions, packet alignment, or duration is invalid", file=sys.stderr)
        return 1
    if has_audio and not any(stream.get("codec_type") == "audio"
                             for stream in result_info["streams"]):
        print("Output TS lost its audio stream", file=sys.stderr)
        return 1
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(args.output), "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if decoded.returncode:
        print(f"Output TS decode failed: {decoded.stderr}", file=sys.stderr)
        return 1
    if args.mode == "dvbs2":
        offline = subprocess.run(
            [str(args.s2_backend), "--input", str(args.output),
             "--symbol-rate", str(symbol_rate), "--fec", args.fec],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if offline.returncode:
            print(f"Offline DVB-S2 modulation failed: {offline.stderr}", file=sys.stderr)
            return 1
        if offline.stderr.strip():
            print(offline.stderr.strip().splitlines()[-1])
    print(f"Validated {actual_duration:.3f}s of {expected_codec} TS; no RF transmission")
    return 0


if __name__ == "__main__":
    sys.exit(main())
