![portsdown banner](/doc/img/Portsdown_4.jpg)
# Portsdown Buster Build For RPi 4

## Trixie development status (22 November 2026)

The `arm64-transmitter` branch contains work toward **two distinct targets**.
Neither is an installable, RF-verified Trixie release. The installer and
instructions below this section are for the legacy **32-bit Buster** release;
do **not** run `install_portsdown.sh` or `update.sh` on Trixie.

| Target | Implemented and checked | Not yet verified |
| --- | --- | --- |
| Pi 4, Raspberry Pi OS Trixie Lite **32-bit (`armhf`)**, original 7-inch 800×480 display | NTSC FFmpeg MPEG-TS path for analog/webcam input, encoder selection, GUI framebuffer/touchscreen fixes, and an installer guard. EasyCap is NTSC-only in this fork. Offline TS tests passed; hardware H.264 encoding was demonstrated on a separate **64-bit** Pi 4. | Boot/build on the actual 32-bit target, original display and touch, capture devices, GUI runtime, installer/update, and RF output. |
| Pi 4, Trixie **64-bit (`arm64`)**, DATV-Express USB board | Native AArch64 `rpidatv`, DVB-T2 stack, DVB-S `express_server`, and updated touchscreen GUI builds. Experimental DVB-S2 backend generated I/Q offline. A separate SRT TX supervisor started the backend only after valid live video TS and stopped it on disconnect or packet stall in TANK dry-run tests. | Physical touchscreen/Web Control runtime, DATV-Express USB enumeration, firmware, sustained I/Q, PTT, decoded DVB-S2/RF, and actual ATEM input. TANK has no board or framebuffer; no RF was transmitted. |

The current GUI and Express S2 backend also built from a **fresh clone** of
the published branch on TANK; its dry-run SRT gate/disconnect check passed.
That is a clean-checkout software check, **not a fresh Pi OS installation**.

The GUI's Video Source menu includes **Pi Cam** for 480p and 720p. With
`h264backend=ffmpeg`, its H.264 and MPEG-2 encoder paths now use `rpicam-vid`
and system FFmpeg instead of the Buster camera stack. A TANK IMX708-derived
recording and a simulated raw camera pipe produced decodable TS offline.
TANK's rover owns the actual camera, so direct `rpicam-vid` capture,
touchscreen transmission, and RF remain unverified.
The same capture helper also handles NTSC EasyCap and webcam MPEG-2 through
V4L2; it selects MJPEG input for a webcam that advertises it. Device-level
capture and RF for those paths still need testing on the intended Pi.

**DVB-S2 distinction:** the legacy `express_server` is **DVB-S only**. With
**Source: SRT**, either the original **Express** or the separate **Express S2**
GUI output selects the experimental DVB-S2 QPSK path. The modern Express
capture route also accepts Pi Cam, NTSC composite, webcam/C920, HDMI V4L2,
and selected test cards for DVB-S or experimental DVB-S2 QPSK. Its
[`src/express_s2` backend](src/express_s2/express_s2.cpp) generates DVB-S2 I/Q
and uses raw-16 USB, but has not been tested with a board. Neither 32-bit nor
64-bit Portsdown has verified DVB-S2 transmission through DATV-Express.
The modern local-source route is **offline-tested with a test card only**;
physical capture, audio, USB, RF, and display operation still need tests.
See the [source/output matrix and porting scope](doc/trixie-mode-porting-scope.md).

### Remaining work

1. **32-bit Trixie:** test a spare Pi 4 image with the original display,
   capture device, and intended RF hardware; finish the modern installer,
   GUI/input path, direct Pi Cam and remaining video sources, and
   install/update regression.
2. **64-bit transmitter:** validate the Pi 4 DMA and RF path, port remaining
   ARM32-only components, and test the intended output devices, especially
   Pluto/LibreSDR and Streamer as separate workstreams. A native
   build and offline modulation do not establish a working transmitter.
3. **DATV-Express DVB-S2:** connect the board to TANK with an appropriate
   dummy load or attenuated receiver; verify raw-16 firmware, USB pacing,
   errors, PTT/stop behavior, and a decoded RF signal. The separate GUI mode
   and SRT interlock now build, but still require display and hardware tests.
4. **SRT/ATEM:** capture the actual feed, measure bitrate and codecs, verify
   live transcode timing at 480p/720p/1080p, and integrate the low-res return
   with the interlocked TX listener. Only one process can bind SRT port 9000.

Detailed status, build evidence, and acceptance gates:
[32-bit NTSC/Trixie migration](doc/ntsc-trixie-migration.md),
[64-bit transmitter and DATV-Express DVB-S2](doc/arm64-transmitter.md), and
[SRT ingest](doc/srt-express-ingest.md), and
[interlocked SRT TX](doc/srt-interlocked-tx.md).

The MSE-88 OBS to TANK SRT/offline DVB-S2 test path is documented in
[MSE-88 OBS SRT to TANK](doc/mse88-obs-srt-to-tank.md).
The separate [Portsdown IP Output/SRT confidence link](doc/ipts-srt-link.md)
keeps BATC Streamer RTMP/FLV intact and adds SRT as an optional live MPEG-TS
transport to another system's IPTS Monitor. IPTS input to DATV-Express
DVB-S or experimental DVB-S2 QPSK now has a live-video TX gate and
loss-triggered RF stop for raw UDP or SRT TS. The armed UDP listener stays
bound while idle, so a source can begin later without keying RF prematurely.
Other IPTS RF outputs fail
closed. The separate 426×240 OBS return at port 9015 displays SMPTE bars
with **NO IP INPUT** until valid live video arrives, then switches back on
loss. These paths passed bounded offline tests only; board/PTT/RF behavior
and physical GUI operation still need hardware tests.
It now has bounded TS-preparation profiles for **DVB-S 2222 ksym/s,
MPEG-2/480p** and **DVB-S2 1000 ksym/s, H.264/480p, 720p, or 1080p**,
with selectable FEC for capacity sizing. A repeatable
[ATEM-like SRT sender](scripts/atem_srt_emulator.sh) and
[bounded TANK listener](scripts/srt_datv_ts_listener.py) pass MSE-88 →
SRT → TANK → DVB-S MPEG-2/480p or DVB-S2 H.264/480p, 720p, and 1080p TS.
MSE-88 now has three tested native OBS SRT Streaming profiles; the older
crash-prone Custom FFmpeg Recording profiles were archived. Actual OBS
captures passed full TS decode and offline DVB-S2 modulation at all three
rasters, 1 Msym/s FEC 1/2. The DVB-S 480p mux timing was corrected and its
actual OBS capture now passes. These are bounded software tests, **not RF
transmission**. Actual ATEM input and board/RF output remain untested.

TANK also serves a low-resolution H.264/AAC confidence return at
`http://192.168.3.33:9013/return.ts` for an OBS Media Source. It shows
generated **NO Signal YET!!!** bars at rest, live incoming SRT video while
available, and the bars again when SRT stops. It never loops a saved TS file.
This previews the source, not the shaped TS or RF output. See the
[live-return instructions](doc/mse88-obs-srt-to-tank.md#low-resolution-encoder-return-from-tank-to-obs).

For a fresh 32-bit Trixie Pi, use the
[isolated first-run and C920 MJPEG test](doc/trixie-32bit-first-run.md). This is
not a full Portsdown installer.

**The Portsdown 4** is a DVB-S and DVB-S2 digital television system for the Raspberry Pi 4.  The core of the system was written by Evariste Courjaud F5OEO and is maintained by him.  This BATC Version, known as the Portsdown, has been developed by a team of BATC members for use with a LimeSDR, Pluto or a DATV Express PCB and a MiniTiouner or Knucker tuner.  The intention is that the design should be reproducible by someone who has never used Linux before.  Detailed instructions on loading the software are listed below, and further details of the complete system design and build are on the BATC Wiki at https://wiki.batc.org.uk/The_Portsdown_Transmitter.  There is a Forum for discussion of the project here: https://forum.batc.org.uk/viewforum.php?f=103

This version is based on Raspberry Pi OS Buster Lite and is only compatible with the Raspberry Pi 4 and 7 inch screen (or DFRobot 5 inch DSI Screen).

Our thanks to Evariste, Heather, Charles and all the other contributors to this community project.  All code within the project is GPL.

KG6MDW's [Buster/Lime Mini C920x, analog, and Camlink test results](doc/buster-limemini-test-results.md) are reproduced below; they do not establish Trixie or DATV-Express S2 hardware compatibility.

# Known working Input, output and Encoding settings

| Video Source| Video Format | TX Hardware | Modulation[^1] | Encoder | Txt overlay? | Supported FPS | Quality Scale | Works with W6CX |
| :---------: | :----------: | :---------: | :----------: | :-----: | :------------: | :-----------: | :--------: | :--------: |
| Comp Vid | 4:3 (480p)   | Lime Mini | DVB-S  | MPEG-2   | Yes      | 29.97| Average| Yes, Both inputs |
| Comp Vid | 4:3 (480p)   | Lime Mini | DVB-S2 | MPEG-2   | Yes      | 30   | Average| Yes, Both inputs |
| Comp Vid | 4:3 (480p)   | Lime Mini | DVB-S2 | H264    | No       | 30   | Average| Yes, Both inputs |
| Logitech C920X[^2] | 4:3 (480p)[^3] | Lime Mini | DVB-S  | MPEG-2   | Yes      | 30   | Good| Yes, Both inputs |
| Logitech C920X[^2] | 4:3 (480p)[^3] | Lime Mini | DVB-S2 | MPEG-2   | Yes      | 30   | Good| Yes, Both inputs |
| Logitech C920X[^2] | 4:3 (D1)[^4]   | Lime Mini | DVB-S2 | H264    | No       | 30   |   Good  | Yes, Both inputs |
| Logitech C920X[^2] | 720P  | Lime Mini | DVB-S  | MPEG-2   | Yes       | 10   | Good, Low FPS | NO |
| Elgato Camlink 4K [^5] | 4:3 (480p) | Lime Mini | DVB-S | MPEG-2   | No       | 30   | Good, Aspect ratio compressed | Yes, Both inputs |
| Elgato Camlink 4K [^5] | 720P| Lime Mini | DVB-S | MPEG-2    | No       | 30   | Good to Great, Limited by synbol rate  | Not recomended, 1273 only |
| Elgato Camlink 4K [^5] | 1080P | Lime Mini | DVB-S | MPEG-2   | No       | 30   | Good to Great, Limited by synbol rate | Not recomended, 1273 only |
| Elgato Camlink 4K [^5] | 4:3 (480p) | Lime Mini | DVB-S2| MPEG-2    | No       | 30   | Good, Aspect ratio compressed |  Yes, 1273 only |
| Elgato Camlink 4K [^5] | 720P | Lime Mini | DVB-S2 | MPEG-2    | No       | 30   | Good, Limited by synbol rate  | Not recomended, 1273 only |
| Elgato Camlink 4K [^5] | 1080P | Lime Mini | DVB-S2 | H264  | No       | 30   | Average, Limited by synbol rate |Not recomended, 1273 only |
| Elgato Camlink 4K [^5] | 4:3 (480p) | Lime Mini | DVB-S2| H264   | No       | 30   | Good, Aspect ratio compressed | Yes, 1273 only |
| Elgato Camlink 4K [^5] | 720P | Lime Mini | DVB-S2 | H264   | No       | 30   | Great | Yes, 1273 only |
| Elgato Camlink 4K [^5] | 1080P | Lime Mini | DVB-S2 | H264  | No       | 30   | Great to Amazing, Depends on synbol rate | Yes, 1273 only |


[^1]: For Modulation, We've only tested DVB-S vs S2, not each subtype of S2 (IE QPSK, 8PSK, 16PSK) or each FEC, as this doesn't really matter - It just increases the available bandwidth (and thus quality at 720p/1080p), and handles link-quality (FEC) The main item here is that S and S2 work with MPEG2 and H264.

[^2]: The device tested was bought from Amazon on 11/20/2026, so it's the latest version. There are limits to it's resolution, and video format. Most cameras run MJPEG and devices convert it, however with how portsdown is done, H264 can't do this, It only supports YUYV or YUV420 - normal broadcast image formats. When the camera runs in YUYV mode, above 800x448 FPS drops off dramatically. At 720p it's 10FPS, and 1080p it's 5fps. Using MJPEG is not available at this time due to the old firmware/software.

[^3]: The Logitech C920x does not support normal 480p or 480i natively. This is 864x480 MJPEG cut down to 720p.

[^4]: The Logitech C920x does not support normal 480p or 480i natively. This is re-sized 640x480 being handled by the avc2ts encoder, and can not be fixed due to footnote 2 above.

[^5]: The Elgato Camlink 4K was tested with a 1080p input video from a laptop. The device supports 480p,720p,1080p and 2160p inputs (and some others).  It scales video on device, and Portsdown selects one of the first 3 video sizes. While 720p and 1080p work, they do drop some frames, fast motion may be blurry.

Item of warning: Analog in (CompVid) does NOT support 720p, or 1080p. You can play with the 16:9 but it's a non-standard resolution and depending on how your repeater is setup (I.E Breaks back down to analog video vs all digital) it can cause squished video.

## What DOES NOT work, and with this build, and will probably never be supported on this base OS. (and why)


- Analog on any mode besides 4:3 - Because we're no doing any up conversion on the portsdown.
- Logitech C920x H264 720P or 1080P. This is due the H264 encoder needing the YUVU/YUV420 color space, and the camera can't physically do this at 30fps. It can do 720p @ 10fps, and 1080p @ 5fps. The camera does support MJPEG, but due to firmware and software limits, I can't modify the avs2ts encoder that is used to work with this image format. Trixie will fix this, as we're going to use FFMPEG for everything. This is why it's in B&W or doesn't work at all.
- Any of the 16:9 modes. This is a PAL one-off format that we don't use here.
- Test Cards - This is because it uses the screen resolutions, and the repeater doesn't do well with conversions.



# Installation for BATC Portsdown RPi 4 Version

The preferred installation method only needs a Windows PC connected to the same (internet-connected) network as your Raspberry Pi.  Do not connect a keyboard or HDMI display directly to your Raspberry Pi.

- First download the 2023-05-03 release of Raspberry Pi OS Lite (Legacy) on to your Windows PC from here
https://downloads.raspberrypi.org/raspios_oldstable_lite_armhf/images/raspios_oldstable_lite_armhf-2023-05-03/2023-05-03-raspios-buster-armhf-lite.img.xz

- Unzip the image (using 7zip as it is a .xz compressed file) and then transfer it to a Micro-SD Card using Win32diskimager https://sourceforge.net/projects/win32diskimager/ or Raspberry Pi Imager. For this legacy Buster procedure, leave the username as `pi`.

- Before you remove the card from your Windows PC, look at the card with windows explorer; the volume should be labeled "boot".  Create a new empty file called ssh in the top-level (root) directory by right-clicking, selecting New, Text Document, and then change the name to ssh (not ssh.txt).  You should get a window warning about changing the filename extension.  Click OK.  If you do not get this warning, you have created a file called ssh.txt and you need to rename it ssh.  IMPORTANT NOTE: by default, Windows (all versions) hides the .txt extension on the ssh file.  To change this, in Windows Explorer, select File, Options, click the View tab, and then untick "Hide extensions for known file types". Then click OK.

- If you have a Pi Camera and/or touchscreen display, you can connect them now.  Power up the RPi with the new card inserted, and a network connection.  Do not connect a keyboard or HDMI display to the Raspberry Pi.

- Find the IP address of your Raspberry Pi using an IP Scanner (such as Advanced IP Scanner http://filehippo.com/download_advanced_ip_scanner/ for Windows, or Fing on an iPhone) to get the RPi's IP address

- From your windows PC use Putty (http://www.chiark.greenend.org.uk/~sgtatham/putty/download.html) to log in to the IP address that you noted earlier.  You will get a Security warning the first time you try; this is normal.

- Log in (user: pi, password: raspberry) then cut and paste the following code in, one line at a time:


```sh
wget https://raw.githubusercontent.com/Marx1/portsdown4_NTSC/master/install_portsdown.sh
chmod +x install_portsdown.sh
./install_portsdown.sh -u Marx1
```

The initial build can take between 45 minutes and one hour, however it does not need any user input, so go and make a cup of coffee and keep an eye on the touchscreen.  When the build is finished the Pi will reboot and start-up with the touchscreen menu.

Once installed. Access the portsdown menu via /home/pi/rpidatv/scripts/menu.sh
