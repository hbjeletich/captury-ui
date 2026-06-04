# captury-ui

PySide6 desktop app that connects to [Captury Live](https://captury.com), receives motion capture data via [RemoteCaptury](https://github.com/hbjeletich/RemoteCaptury), and forwards pose/angle data as OSC to TouchDesigner or any OSC receiver.

## Running from source

```bash
pip install -r requirements.txt
python main.py
```

Copy `config.example.json` to `config.json` and fill in your Captury Live host IP and the path to `bridge.exe`.

## macOS: Gatekeeper warning

The app is ad-hoc signed but not notarized, so macOS may still block it on first launch. To clear the quarantine flag on the entire bundle at once:

```bash
xattr -rd com.apple.quarantine /path/to/captury-ui
```

Then launch normally.
