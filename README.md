# captury-ui

**Captury Student Streamer** — a desktop app that takes live motion-capture data out of Captury Live and forwards it to TouchDesigner (or any other OSC receiver). It's the tool you run to get a tracked person's joints and biomechanical angles into your project.

If you just want to use it, you do **not** need to build anything or understand the code below. Download a release and go.

---

## How it all fits together

```
  Captury Live            RemoteCaptury            captury-ui              Your project
 (the mocap system)   ->   "bridge"          ->   (this app)        ->    TouchDesigner /
  tracks a person          streams pose data       picks joints,           any OSC receiver
  in the room              over the network         sends OSC
```

- **Captury Live** is the motion-capture software running on the lab machine. It tracks people in the room and produces skeletons.
- **The bridge** is a small program (from the [RemoteCaptury](https://github.com/hbjeletich/RemoteCaptury) project) that connects to Captury Live and streams the pose data out. **It comes bundled inside the release**, so you don't have to think about it.
- **captury-ui** (this app) shows you the skeleton, lets you choose which joints and angles you care about, and sends them out as OSC messages.
- **Your project** — usually TouchDesigner — receives those OSC messages and does something with them.

So the only piece you interact with is this app. Everything to its left is plumbing that the release takes care of.

---

## Quick start (recommended — no building)

1. Go to the [Releases page](https://github.com/hbjeletich/captury-ui/releases) and download the build for your operating system:
   - **Windows** — `captury-ui-windows-x64`
   - **macOS** — `captury-ui-macos-arm64`
2. Unzip it anywhere and launch the app. The bridge is already included in the download.
3. In the app, set the **Host** to the IP address of the machine running Captury Live, and leave the **Port** at `2101` (the Captury default).
4. Press connect. When a person is tracked, you'll see their skeleton appear.
5. Choose the joints and angles you want, add an OSC destination pointing at your project, and you're streaming.

> **macOS first-launch warning:** the app is signed but not notarized, so macOS may block it the first time. If it refuses to open, clear the quarantine flag on the whole app once:
> ```bash
> xattr -rd com.apple.quarantine /path/to/captury-ui
> ```
> Then launch it normally.

---

## Using the app

- **Skeleton view** — a live 3D view of the tracked person, so you can confirm the connection is working.
- **Camera view** — the camera feed from Captury.
- **Actors** — if more than one person is tracked, pick which one you're streaming.
- **Joints** — check the joints you want to send. Only the ones you select get streamed, which keeps your OSC traffic clean.
- **Biomechanical Angles** — a filterable table of joint angles (knee flexion, hip abduction, torso inclination, etc.). Select the ones you need.
- **Recording** — start/stop recording and name shots in Captury Live remotely, without leaving the app.
- **Destinations** — one or more OSC targets. Each has an IP, a port, an address template, and an on/off toggle, so you can send to several receivers at once (e.g. two laptops).

### OSC message format

By default each value is sent to an address built from this template:

```
/captury/{actor}/{joint}
```

`{actor}` is replaced with the tracked person's ID and `{joint}` with the joint or angle name. You can change the template per destination if your receiver expects a different address layout.

---

## Testing without the mocap system (`--fake` mode)

You don't need to be in the lab, or have Captury running, to build the receiving side of your project. Run the app in **fake mode** and it generates a synthetic moving skeleton with realistic joints and angles, streamed over OSC exactly like the real thing:

```bash
python main.py --fake
```

This is the easiest way to develop and test your TouchDesigner patch at home. When you get to the lab, drop the `--fake` flag (or use the release build) and point it at the real Captury host.

---

## Configuration

The app reads a `config.json` next to it (create it from `config.example.json`). You can also set everything in the UI — the file just lets you save defaults.

```json
{
  "host": "192.168.1.100",
  "port": 2101,
  "bridge_exe": "C:\\path\\to\\bridge.exe",
  "destinations": [
    {
      "ip": "127.0.0.1",
      "port": 7000,
      "template": "/captury/{actor}/{joint}",
      "enabled": true
    }
  ]
}
```

- **host / port** — where Captury Live is running (`2101` is the default port).
- **bridge_exe** — path to the bundled bridge. In a release build this is filled in for you; you only set it when running from source.
- **destinations** — your OSC targets (matches the Destinations panel in the UI).

---

## Running from source (only if you're modifying the app)

Most students never need this. It's here for anyone extending the tool.

```bash
pip install -r requirements.txt
python main.py
```

Requirements are just `PySide6` and `python-osc`.

When running from source you also need the **bridge** program, which lives in the [RemoteCaptury](https://github.com/hbjeletich/RemoteCaptury) repo. Build it there, then point `bridge_exe` in your `config.json` at the resulting `bridge` / `bridge.exe`. (The GitHub Actions workflow in `.github/workflows/build.yml` does exactly this to produce the releases — it checks out RemoteCaptury, builds the bridge, bundles it with the app, and packages it for Windows and macOS.)

---

## Related projects

- **[RemoteCaptury](https://github.com/hbjeletich/RemoteCaptury)** — the library and bridge that feed this app.
- **[CapturyUnityToolkit](https://github.com/hbjeletich/CapturyUnityToolkit)** — if your project is in Unity instead of TouchDesigner, use that toolkit to bring Captury data into Unity's Input System.
