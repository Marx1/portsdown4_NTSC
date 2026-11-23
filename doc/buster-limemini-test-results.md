# Buster / Lime Mini capture results reported by KG6MDW

The following matrix and notes come from [KG6MDW's 343c9df change](https://github.com/Marx1/portsdown4_NTSC/commit/343c9df11554453ea4f07f9396d80b291ef370da). They describe his Buster setup with a Lime Mini and W6CX receiver, **not** a validation of the Trixie or DATV-Express S2 paths. The C920x MJPEG capture and NTSC fixes have been integrated into this branch, but hardware results have not been reproduced here.

Integration check: a synthetic 864×480/30 fps source passed the new center
crop, 8:9 sample-aspect ratio, denoise, MPEG-2, and MP2 audio filter path;
the resulting 720×480 TS decoded without errors. This checks FFmpeg filter
construction, **not** C920x capture, Lime Mini output, or RF.

| Video Source   | Video Format | Modulator Hardware | Modulation[^1] | Encoder | Text overlay supported? | Supported FPS | Quality Scale | Works with W6CX |
| :------------: | :----------: | :----------------: | :----------: | :-----: | :---------------------: | :-----------: | :-----------: | :-----------: |
| Comp Vid       | 4:3 (480p)   | Lime Mini          | DVB-S        | MPEG-2   | Yes                     | 29.97         | Average      | Yes, Both inputs |
| Comp Vid       | 4:3 (480p)   | Lime Mini          | DVB-S2       | MPEG-2   | Yes                     | 30            | Average      | Yes, Both inputs |
| Comp Vid       | 4:3 (480p)   | Lime Mini          | DVB-S2       | H264    | No                      | 30            | Average      | Yes, Both inputs |
| Logitech C920X[^2] | 4:3 (480p)[^3] | Lime Mini          | DVB-S        | MPEG-2   | Yes                     | 30            | Good         | Yes, Both inputs |
| Logitech C920X[^2] | 4:3 (480p)[^3] | Lime Mini          | DVB-S2       | MPEG-2   | Yes                     | 30            | Good         | Yes, Both inputs |
| Logitech C920X[^2] | 4:3 (D1)[^4]   | Lime Mini          | DVB-S2       | H264    | No                      | 30            |   Good        | Yes, Both inputs |
| Logitech C920X[^2] | 720P           | Lime Mini          | DVB-S        | MPEG-2   | Yes                      | 10            | Good, Low FPS | NO |
| Elgato Camlink 4K [^5] | 4:3 (480p)       | Lime Mini          | DVB-S       | MPEG-2   | No                      | 30            | Good, Aspect ratio compressed | Yes, Both inputs |
| Elgato Camlink 4K [^5] | 720P      | Lime Mini          | DVB-S       | MPEG-2    | No                      | 30            | Good to Great, Limited by synbol rate  | Not recomended, 1273 only |
| Elgato Camlink 4K [^5] | 1080P       | Lime Mini          | DVB-S       | MPEG-2   | No                      | 30            | Good to Great, Limited by synbol rate | Not recomended, 1273 only |
| Elgato Camlink 4K [^5] | 4:3 (480p)       | Lime Mini          | DVB-S2      | MPEG-2    | No                      | 30            | Good, Aspect ratio compressed |  Yes, 1273 only |
| Elgato Camlink 4K [^5] | 720P       | Lime Mini          | DVB-S2       | MPEG-2    | No                      | 30            | Good, Limited by synbol rate  | Not recomended, 1273 only |
| Elgato Camlink 4K [^5] | 1080P       | Lime Mini          | DVB-S2       | H264  | No                      | 30            | Average, Limited by synbol rate |Not recomended, 1273 only |
| Elgato Camlink 4K [^5] | 4:3 (480p)       | Lime Mini          | DVB-S2      | H264   | No                      | 30            | Good, Aspect ratio compressed | Yes, 1273 only |
| Elgato Camlink 4K [^5] | 720P       | Lime Mini          | DVB-S2       | H264   | No                      | 30            | Great | Yes, 1273 only |
| Elgato Camlink 4K [^5] | 1080P       | Lime Mini          | DVB-S2       | H264  | No                      | 30            | Great to Amazing, Depends on synbol rate | Yes, 1273 only |


[^1]: For Modulation, We've only tested DVB-S vs S2, not each subtype of S2 (IE QPSK, 8PSK, 16PSK) or each FEC, as this doesn't really matter - It just increases the available bandwidth (and thus quality at 720p/1080p), and handles link-quality (FEC) The main item here is that S and S2 work with MPEG2 and H264.

[^2]: Trevor tested a C920x purchased on 20 November 2026. There are limits to it's resolution, and video format. Most cameras run MJPEG and devices convert it, however with how portsdown is done, H264 can't do this, It only supports YUYV or YUV420 - normal broadcast image formats. When the camera runs in YUYV mode, above 800x448 FPS drops off dramatically. At 720p it's 10FPS, and 1080p it's 5fps. Using MJPEG is not available at this time due to the old firmware/software.

[^3]: The Logitech C920x does not support normal 480p or 480i natively. This is 864x480 MJPEG center-cropped to 720x480.

[^4]: The Logitech C920x does not support normal 480p or 480i natively. This is re-sized 640x480 being handled by the avc2ts encoder, and can not be fixed due to footnote 2 above.

[^5]: The Elgato Camlink 4K was tested with a 1080p input video from a laptop. The device supports 480p,720p,1080p and 2160p inputs (and some others).  It scales video on device, and Portsdown selects one of the first 3 video sizes. While 720p and 1080p work, they do drop some frames, fast motion may be blurry.

Item of warning: Analog in (CompVid) does NOT support 720p, or 1080p. You can play with the 16:9 but it's a non-standard resolution and depending on how your repeater is setup (I.E Breaks back down to analog video vs all digital) it can cause squished video.
