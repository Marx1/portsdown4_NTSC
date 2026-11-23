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

    def config(self, transport, s2):
        path = self.path / "config"
        path.write_text(
            "modeinput=IPTSIN\n"
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

    def exercise(self, transport, s2):
        config = self.config(transport, s2)
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
        command = ["python3", "-B", str(SUPERVISOR), "--config", str(config),
                   "--pid-file", str(self.path / "pid"), "--dry-run", "--no-preview",
                   "--preview-udp-port", str(free_port())]
        if s2:
            command += ["--backend", str(backend)]
        with (self.path / "log").open("w") as log:
            supervisor = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                self.wait_log("RF off until valid live video TS")
                self.assertNotIn("Valid IPTS video", (self.path / "log").read_text())
                time.sleep(0.5)  # let FFmpeg bind the SRT/UDP input socket
                url = (f"srt://127.0.0.1:{self.port}?mode=caller&latency=200000" if transport == "srt"
                       else f"udp://127.0.0.1:{self.port}?pkt_size=1316")
                sender = subprocess.Popen(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi",
                     "-i", "testsrc2=size=320x240:rate=15", "-c:v", "libx264", "-preset",
                     "ultrafast", "-b:v", "250k", "-g", "15", "-x264-params",
                     "repeat-headers=1", "-f", "mpegts", url],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                try:
                    self.wait_log("Valid IPTS video", timeout=10)
                    if s2:
                        self.wait_log("FAKE BACKEND STARTED")
                finally:
                    sender.terminate()
                    sender.wait(timeout=5)
                self.wait_log("IPTS RF stopped; waiting for new live input", timeout=7)
                self.assertIsNone(supervisor.poll(), "supervisor should remain armed, RF off")
            finally:
                supervisor.send_signal(signal.SIGTERM)
                supervisor.wait(timeout=8)

    def test_udp_dvbs_gate_and_loss(self):
        self.exercise("udp", False)

    def test_srt_dvbs2_gate_and_disconnect(self):
        self.exercise("srt", True)

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
