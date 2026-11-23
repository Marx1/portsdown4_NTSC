#!/usr/bin/env python3
"""Create a separate OBS FFmpeg-output profile for SRT MPEG-TS.

Does not modify or switch the active OBS profile or restart OBS.
"""

import argparse
import configparser
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-profile", required=True, help="existing OBS profile directory name")
    parser.add_argument("--profile-name", required=True, help="new profile directory and display name")
    parser.add_argument("--srt-url", required=True, help="SRT caller URL for the receiver")
    args = parser.parse_args()

    if not args.srt_url.startswith("srt://") or "mode=caller" not in args.srt_url:
        parser.error("--srt-url must be an srt:// caller URL")
    if Path(args.profile_name).name != args.profile_name:
        parser.error("--profile-name must be a single directory name")

    profiles = Path.home() / ".config/obs-studio/basic/profiles"
    source = profiles / args.source_profile
    target = profiles / args.profile_name
    if not (source / "basic.ini").is_file():
        parser.error(f"source OBS profile not found: {source}")
    if target.exists():
        parser.error(f"target profile already exists: {target}")

    shutil.copytree(source, target, ignore=shutil.ignore_patterns("service.json", "service.json.bak"))
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(target / "basic.ini")
    if not config.has_section("General"):
        config.add_section("General")
    if not config.has_section("Output"):
        config.add_section("Output")
    if not config.has_section("AdvOut"):
        config.add_section("AdvOut")

    config["General"]["Name"] = args.profile_name.replace("_", " ")
    config["Output"]["Mode"] = "Advanced"
    config["AdvOut"].update({
        "RecType": "FFmpeg",
        "FFOutputToFile": "false",
        "FFURL": args.srt_url,
        "FFFormat": "mpegts",
        "FFFormatMimeType": "video/MP2T",
        "FFVEncoder": "libx264",
        "FFVEncoderId": "27",  # AV_CODEC_ID_H264
        "FFVBitrate": "600",  # OBS uses kbit/s here
        "FFVGOPSize": "48",
        "FFRescale": "true",
        "FFRescaleRes": "640x360",
        "FFAEncoder": "aac",
        "FFAEncoderId": "86018",  # AV_CODEC_ID_AAC
        "FFABitrate": "64",  # kbit/s
        "FFAudioMixes": "1",
    })

    temp = target / "basic.ini.tmp"
    with temp.open("w") as handle:
        # OBS's own config parser expects Key=Value (no spaces around '=').
        config.write(handle, space_around_delimiters=False)
    temp.replace(target / "basic.ini")

    # The FFmpeg output does not use an RTMP service. Blank the inherited
    # stream service so Start Streaming cannot accidentally use its old key.
    (target / "service.json").write_text(json.dumps({
        "type": "rtmp_custom",
        "settings": {"server": "", "key": "", "use_auth": False},
    }, indent=2) + "\n")
    print(f"Created {target}")
    print("Select this profile in OBS; Advanced > Recording > Custom Output (FFmpeg) sends SRT.")
    print("The control is Start Recording, although the destination is a network stream.")


if __name__ == "__main__":
    main()
