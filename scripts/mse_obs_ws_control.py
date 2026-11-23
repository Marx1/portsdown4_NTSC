#!/usr/bin/env python3
"""Control local OBS-WebSocket for bounded DATV profile checks on MSE-88.

Reads OBS's local password from global.ini; never prints or stores it.
Requires the system python3-websockets package. Connects only to localhost.
"""

import argparse
import asyncio
import base64
import configparser
import hashlib
import json
from pathlib import Path

import websockets


def auth_response(password, salt, challenge):
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


async def run(action, profile):
    config = configparser.ConfigParser(interpolation=None)
    config.read(Path.home() / ".config/obs-studio/global.ini")
    password = config["OBSWebSocket"]["ServerPassword"]
    async with websockets.connect("ws://127.0.0.1:4455", open_timeout=5) as ws:
        hello = json.loads(await ws.recv())
        auth = hello["d"].get("authentication")
        identify = {"rpcVersion": 1}
        if auth:
            identify["authentication"] = auth_response(
                password, auth["salt"], auth["challenge"])
        await ws.send(json.dumps({"op": 1, "d": identify}))
        identified = json.loads(await ws.recv())
        if identified.get("op") != 2:
            raise RuntimeError("OBS-WebSocket authentication failed")

        async def request(request_type, data=None):
            await ws.send(json.dumps({"op": 6, "d": {"requestType": request_type,
                           "requestId": request_type, "requestData": data or {}}}))
            while True:
                result = json.loads(await ws.recv())
                if result.get("op") == 7 and result["d"].get("requestId") == request_type:
                    response = result["d"]
                    if not response["requestStatus"]["result"]:
                        raise RuntimeError(f"{request_type}: {response['requestStatus']}")
                    return response.get("responseData", {})

        if action == "status":
            profiles = await request("GetProfileList")
            stream = await request("GetStreamStatus")
            video = await request("GetVideoSettings")
            print(json.dumps({"profile": profiles["currentProfileName"],
                              "streaming": stream["outputActive"],
                              "skipped_frames": stream.get("outputSkippedFrames"),
                              "video": video}))
        elif action == "profile":
            await request("SetCurrentProfile", {"profileName": profile})
            print((await request("GetProfileList"))["currentProfileName"])
        else:
            await request("StartStream" if action == "start" else "StopStream")
            print(json.dumps(await request("GetStreamStatus")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "profile", "start", "stop"))
    parser.add_argument("profile", nargs="?")
    args = parser.parse_args()
    if args.action == "profile" and not args.profile:
        parser.error("profile name required")
    asyncio.run(run(args.action, args.profile))
