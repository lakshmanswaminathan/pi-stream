# Pi Stream Setup Guide

## Mac Setup (one-time)

### 1. Enable Screen Sharing (VNC)
- System Settings → General → Sharing → **Screen Sharing** → ON
- Click the **(i)** info button next to Screen Sharing
- Check **"VNC viewers may control screen with password"**
- Set password to: `stream`
- Under "Allow access for", select **"All users"**

### 2. Disable VNC Timeouts
Run each line separately in Terminal:

```bash
sudo defaults write /Library/Preferences/com.apple.RemoteManagement VNCIdleTimeout -int 0
```

```bash
sudo defaults write /Library/Preferences/com.apple.RemoteManagement VNCInactiveTimeout -int 0
```

```bash
sudo defaults write /Library/Preferences/com.apple.RemoteManagement ScreenSharingReqPermEnabled -bool false
```

```bash
sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart -restart -agent -console
```

### 3. Screen Recording Permission (HD mode only)
- System Settings → Privacy & Security → Screen & System Audio Recording
- Enable **Terminal.app** (not Ghostty — Ghostty sends black frames)
- Quit and relaunch Terminal after enabling

### 4. Install ffmpeg (HD mode only)
```bash
brew install ffmpeg
```

### 5. Find Your IP
```bash
ipconfig getifaddr en0
```

## Slack Commands

| Command | Description |
|---------|-------------|
| `/stream <ip>` | VNC mode — Pi connects to your Mac's Screen Sharing |
| `/stream hd <ip>` | HD mode — you run an ffmpeg command to stream 1080p |
| `/stream stop` | Stop streaming, free the TV |
| `/stream status` | Check who's streaming |

### VNC Mode
Just run `/stream <your-ip>`. The Pi connects automatically. No local commands needed.

- Pros: zero setup on your end (after one-time config above), works instantly
- Cons: higher latency, streams at your native resolution (5K on retina)

### HD Mode
Run `/stream hd <your-ip>`. The bot replies with an ffmpeg command — run it from **Terminal.app**.

- Pros: 1080p scaled, hardware encoding (VideoToolbox), better frame rate
- Cons: requires ffmpeg installed, must run a command locally, Terminal.app only

## Improving Performance

### Best: Ethernet
Plug the Pi into your router/switch via ethernet cable. Eliminates wifi overhead entirely.

### Good: Lower Mac Display Resolution
System Settings → Displays → pick "More Space" or a lower resolution. VNC sends raw pixels so fewer pixels = faster updates. Your workspace stays usable, just smaller elements.

### OK: Use HD Mode
`/stream hd <ip>` scales to 1080p before sending, uses hardware encoding. Better frame rate than VNC over wifi.

## Pi Details

| Pi | Hostname | IP | MAC |
|----|----------|-----|-----|
| 1 | raspberrypi.local | 192.168.1.28 | 2c:cf:67:e0:fa:2c |
| 2 | raspberrypi-2.local | 192.168.1.195 | 2c:cf:67:e6:f2:a |
| 3 | raspberrypi-3.local | 192.168.1.88 | 2c:cf:67:c3:f4:67 |

**TV Pi (active):** Pi 1 at `192.168.1.28` (hostname: `flt-pi-3`)

## Troubleshooting

**"Failed to connect"** — Screen Sharing not enabled, or wrong IP. Run `ipconfig getifaddr en0`.

**Black screen in HD mode** — Screen Recording permission not granted to your terminal app. Use Terminal.app, not Ghostty.

**Laggy/slow updates** — Use ethernet, lower display resolution, or switch to HD mode.

**Connection drops every 60s** — The bot auto-reconnects. If it stops, run `/stream stop` then `/stream <ip>` again.

**"Unknown security result"** — This happens when using PasswordFile auth. The bot uses expect-based auth which works around this macOS quirk.
