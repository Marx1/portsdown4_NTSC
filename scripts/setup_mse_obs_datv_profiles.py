#!/usr/bin/env python3
"""Replace MSE-88's experimental DATV OBS profiles with native SRT Streaming profiles.

Run as the desktop user with OBS closed. Keeps a timestamped backup of every
DATV profile and launcher; leaves BAM 2023 and scene collections untouched.
"""

import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess


MODES = {
    "480": ("DATV SRT TANK STREAM 480", 854, 480, 600, 64, 24, "veryfast"),
    "720": ("DATV SRT TANK STREAM 720", 1280, 720, 2000, 96, 24, "veryfast"),
    "1080": ("DATV SRT TANK STREAM 1080", 1920, 1080, 3500, 96, 15, "superfast"),
}
LEGACY = ("DATV_SRT_TANK", "DATV_SRT_TANK_480",
          "DATV_SRT_TANK_720", "DATV_SRT_TANK_HD")


def set_values(text, section, updates):
    match = re.search(rf"(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)", text)
    if not match:
        raise ValueError(f"missing [{section}] in OBS profile")
    body = match.group(1)
    for key, value in updates.items():
        pattern = rf"(?m)^{re.escape(key)}=.*$"
        if re.search(pattern, body):
            body = re.sub(pattern, f"{key}={value}", body, count=1)
        else:
            body = body.rstrip("\n") + f"\n{key}={value}\n\n"
    return text[:match.start(1)] + body + text[match.end(1):]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    profiles = home / ".config/obs-studio/basic/profiles"
    base = home / "portsdown-srt"
    apps = home / ".local/share/applications"
    template = profiles / "DATV_SRT_TANK_STREAM_480"
    if not (template / "basic.ini").is_file() or not (template / "service.json").is_file():
        parser.error("tested DATV SRT TANK STREAM 480 template is missing")
    if subprocess.run(["pgrep", "-u", str(home.stat().st_uid), "-x", "obs"],
                      stdout=subprocess.DEVNULL).returncode == 0:
        parser.error("close OBS before changing its profile files")

    backup = base / "obs-profile-backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    for name in ("profiles", "launchers", "desktop", "retired-profiles"):
        (backup / name).mkdir(parents=True)
    for path in profiles.glob("DATV_SRT_TANK*"):
        if path.is_dir():
            shutil.copytree(path, backup / "profiles" / path.name)
    for path in base.glob("start-obs-datv*.sh"):
        shutil.copy2(path, backup / "launchers" / path.name)
    for path in apps.glob("obs-datv-srt-tank*.desktop"):
        shutil.copy2(path, backup / "desktop" / path.name)

    original = (template / "basic.ini").read_text()
    service = (template / "service.json").read_bytes()
    # SimpleOutput uses OBS's native x264/AAC Streaming path. The old AdvOut
    # Custom FFmpeg Recording configuration caused stop-time crashes.
    cleaned = re.sub(r"(?ms)^\[AdvOut\]\n.*?(?=^\[|\Z)", "", original)
    for short, (name, width, height, vbitrate, abitrate, fps, preset) in MODES.items():
        directory = profiles / f"DATV_SRT_TANK_STREAM_{short}"
        directory.mkdir(exist_ok=True)
        config = set_values(cleaned, "General", {"Name": name})
        config = set_values(config, "Video", {
            "OutputCX": width, "OutputCY": height,
            "FPSType": 1, "FPSInt": fps,
        })
        config = set_values(config, "SimpleOutput", {
            "VBitrate": vbitrate, "ABitrate": abitrate,
            "StreamEncoder": "x264", "StreamAudioEncoder": "aac",
            "Preset": preset,
        })
        config = set_values(config, "Output", {
            "Mode": "Simple", "BindIP": "default",
        })
        (directory / "basic.ini").write_text(config)
        (directory / "service.json").write_bytes(service)

    for name in LEGACY:
        directory = profiles / name
        if directory.exists():
            shutil.move(str(directory), str(backup / "retired-profiles" / name))
    for path in apps.glob("obs-datv-srt-tank*.desktop"):
        path.unlink()

    launchers = {
        "start-obs-datv.sh": "480",
        "start-obs-datv-stream.sh": "480",
        "start-obs-datv-480.sh": "480",
        "start-obs-datv-720.sh": "720",
        "start-obs-datv-hd.sh": "1080",
    }
    for filename, mode in launchers.items():
        profile_name = MODES[mode][0]
        script = ("#!/usr/bin/env bash\nset -euo pipefail\n"
                  f"exec {base}/launch_obs_with_srt_ffmpeg.sh \\\n"
                  f"  {base}/ffmpeg-4.2.7-srt-tls \\\n"
                  f"  --profile \"{profile_name}\"\n")
        path = base / filename
        path.write_text(script)
        path.chmod(0o755)
    for short in MODES:
        launcher = {"480": "start-obs-datv-480.sh", "720": "start-obs-datv-720.sh",
                    "1080": "start-obs-datv-hd.sh"}[short]
        desktop = ("[Desktop Entry]\nType=Application\n"
                   f"Name=OBS DATV SRT to TANK (Streaming {short}p)\n"
                   "Comment=Native OBS H.264/AAC SRT stream; click Start Streaming\n"
                   f"Exec={base / launcher}\n"
                   "Terminal=false\nCategories=AudioVideo;Video;\n")
        (apps / f"obs-datv-srt-tank-stream-{short}.desktop").write_text(desktop)
    print(f"DATV profiles installed; backup and retired profiles: {backup}")


if __name__ == "__main__":
    main()
