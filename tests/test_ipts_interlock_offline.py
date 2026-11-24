#!/usr/bin/env python3
"""Bounded, board-free proof of the IPTS no-input and loss gates."""

from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "scripts/ipts_interlocked_tx.py"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class IPTSInterlockOfflineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="portsdown-ipts-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.port = free_port()

    def config(self, transport, s2, source="IPTSIN"):
        path = self.path / "config"
        path.write_text(
            f"modeinput={source}\n"
            f"modeoutput={'DATVEXPRESS_S2' if s2 else 'DATVEXPRESS'}\n"
            f"modulation={'S2QPSK' if s2 else 'DVB-S'}\n"
            f"fec={'12' if s2 else '1'}\n"
            "symbolrate=1200\nfreqoutput=437\npidpmt=4095\npidvideo=256\n"
            f"udpinport={self.port}\niptransport={transport}\n"
        )
        return path

    def wait_log(self, needle, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            content = (self.path / "log").read_text()
            if needle in content:
                return content
            time.sleep(0.2)
        self.fail(f"missing {needle!r} in supervisor log: {content}")

    def wait_log_count(self, needle, count, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            content = (self.path / "log").read_text()
            if content.count(needle) >= count:
                return content
            time.sleep(0.2)
        self.fail(f"expected {count} occurrences of {needle!r}: {content}")

    def exercise(self, transport, s2, source="IPTSIN"):
        config = self.config(transport, s2, source)
        backend = self.path / "express_s2" / "fake_backend"
        if s2:
            backend.parent.mkdir()
            (self.path / "dvb_t_stack").mkdir()
            backend.write_text(
                "#!/usr/bin/env python3\nimport sys\n"
                "if '--rate-only' in sys.argv: print(1600000); sys.exit(0)\n"
                "print('FAKE BACKEND STARTED', flush=True)\n"
                "while sys.stdin.buffer.read(188): pass\n"
            )
            backend.chmod(0o755)
        preview_port = free_port()
        command = ["python3", "-B", str(SUPERVISOR), "--config", str(config),
                   "--pid-file", str(self.path / "pid"), "--dry-run", "--no-preview",
                   "--preview-udp-port", str(preview_port), "--input-port", str(self.port)]
        if s2:
            command += ["--backend", str(backend)]
        with (self.path / "log").open("w") as log:
            supervisor = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                self.wait_log("RF off until valid live video TS")
                self.assertNotIn("Valid IPTS video", (self.path / "log").read_text())
                # Start after the old UDP two-second timeout would have
                # expired several times. The armed socket must still be live.
                time.sleep(5)
                self.assertIsNone(supervisor.poll())
                self.assertEqual((self.path / "log").read_text().count(
                    "RF off until valid live video TS"), 1)
                for burst in (1, 2):
                    if burst == 2:
                        time.sleep(3)
                        self.assertIsNone(supervisor.poll(), "re-armed supervisor exited")
                    url = (f"srt://127.0.0.1:{self.port}?mode=caller&latency=200000" if transport == "srt"
                           else f"udp://127.0.0.1:{self.port}?pkt_size=1316")
                    sender = subprocess.Popen(
                        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi",
                         "-i", "testsrc2=size=320x240:rate=15", "-re", "-f", "lavfi",
                         "-i", "sine=frequency=1000:sample_rate=48000", "-c:v", "libx264", "-preset",
                         "ultrafast", "-b:v", "250k", "-g", "15", "-x264-params",
                         "repeat-headers=1", "-c:a", "aac", "-b:a", "48k", "-f", "mpegts", url],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    try:
                        self.wait_log_count("Valid IPTS video", burst, timeout=10)
                        if s2:
                            self.wait_log_count("FAKE BACKEND STARTED", burst)
                        if source == "SRT" and burst == 1:
                            probe = subprocess.run(
                                ["ffprobe", "-v", "error", "-show_entries",
                                 "stream=codec_name,width,height", "-of", "compact",
                                 f"udp://127.0.0.1:{preview_port}?timeout=4000000"],
                                capture_output=True, text=True, timeout=8,
                            )
                            self.assertEqual(probe.returncode, 0, probe.stderr)
                            self.assertIn("codec_name=mpeg2video", probe.stdout)
                            self.assertIn("width=720|height=480", probe.stdout)
                            self.assertIn("codec_name=mp2", probe.stdout)
                    finally:
                        sender.terminate()
                        sender.wait(timeout=5)
                    self.wait_log_count("IPTS RF stopped; waiting for new live input", burst, timeout=7)
                    self.assertIsNone(supervisor.poll(), "supervisor should remain armed, RF off")
            finally:
                supervisor.send_signal(signal.SIGTERM)
                supervisor.wait(timeout=8)

    def test_udp_dvbs_gate_and_loss(self):
        self.exercise("udp", False)

    def test_srt_dvbs2_gate_and_disconnect(self):
        self.exercise("srt", True)

    def test_srt_dvbs_transcodes_to_mpeg2_and_stops(self):
        self.exercise("srt", False, source="SRT")

    def test_unsupported_rf_output_is_blocked(self):
        config = self.config("udp", False)
        config.write_text(config.read_text().replace("DATVEXPRESS", "LIMEMINI"))
        result = subprocess.run(["python3", "-B", str(SUPERVISOR), "--config", str(config),
                                 "--dry-run", "--no-preview"], capture_output=True,
                                text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("other outputs are blocked", result.stderr)


if __name__ == "__main__":
    unittest.main()
