#!/usr/bin/env python3
"""In-process HTTP confidence return for IPTS TX; never connected to RF.

The caller owns ``live`` and forwards *validated* TS to the local UDP port.
The HTTP connection stays open across card/live transitions so OBS can keep
the same Media Source. No file or previous TS is ever replayed.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import select
import subprocess


def preview_command(live, udp_port):
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    if live:
        base += ["-fflags", "nobuffer", "-probesize", "1000000", "-analyzeduration", "1000000",
                 "-i", f"udp://127.0.0.1:{udp_port}?fifo_size=100000&overrun_nonfatal=1&timeout=2000000",
                 "-map", "0:v:0", "-map", "0:a:0?", "-vf", "fps=15,scale=426:240,format=yuv420p"]
    else:
        base += ["-re", "-f", "lavfi", "-i", "smptebars=size=426x240:rate=15",
                 "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                 "-map", "0:v:0", "-map", "1:a:0",
                 "-vf", "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                 "text='NO IP INPUT':fontcolor=black:fontsize=28:box=1:boxcolor=white@0.85:"
                 "boxborderw=9:x=(w-text_w)/2:y=(h-text_h)/2,format=yuv420p"]
    return base + ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                   "-b:v", "220k", "-maxrate:v", "220k", "-bufsize:v", "440k", "-g", "30",
                   "-c:a", "aac", "-b:a", "32k", "-ac", "1", "-ar", "48000",
                   "-muxdelay", "0.1", "-f", "mpegts", "pipe:1"]


def start_preview(bind, port, udp_port, live_event):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/return.ts":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/MP2T")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while not self.server.stopping:
                state = live_event.is_set()
                child = subprocess.Popen(preview_command(state, udp_port), stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL)
                try:
                    while not self.server.stopping and live_event.is_set() == state:
                        ready, _, _ = select.select([child.stdout], [], [], 0.2)
                        if ready:
                            data = os.read(child.stdout.fileno(), 1316 * 16)
                            if not data:
                                break
                            self.wfile.write(data)
                        elif child.poll() is not None:
                            break
                except (BrokenPipeError, ConnectionResetError):
                    return
                finally:
                    if child.poll() is None:
                        child.terminate()
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    child.stdout.close()
                if live_event.is_set() == state:
                    # FFmpeg failed (e.g. missing filter/encoder): close rather
                    # than spin on a broken preview process.
                    return

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    server.stopping = False
    return server
