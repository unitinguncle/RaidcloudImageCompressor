# RaidCloud Immich Suite

**The one-stop solution for compressing and uploading your photos to [Immich](https://github.com/immich-app/immich).**

---

## Features

| Feature | Description |
|---|---|
| ⚡ **Compress & Upload** | Compress images locally (JPEG/PNG, with RAW support) then upload via Immich REST API |
| 🌐 **Google Takeout** | Import Google Takeout archives using `immich-go` |
| 📁 **Local Upload** | Upload any folder with extension/date filters using `immich-go` |
| ⚙ **Settings** | Persist server URL, API key, compression preferences |
| 🔄 **Auto binary** | `immich-go` binary auto-downloaded for your OS/arch on first use |
| 🖱 **Drag & Drop** | Drop folders/zips directly onto the app |

---

## Requirements

- **Python 3.11+**
- pip

## Installation

```bash
cd path/to/ric
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

## Supported Image Formats

JPEG, PNG, CR2, CR3, NEF, NRW, ARW, SR2, SRF, DNG

## Building an Executable

```bash
pip install pyinstaller
pyinstaller main.spec
```
*(Adjust `main.spec` as needed for your platform.)*

## Credits

- Compression UI inspired by [unitinguncle/RaidcloudImageCompressor](https://github.com/unitinguncle/RaidcloudImageCompressor)
- immich-go integration inspired by [shitan198u/immich-go-gui](https://github.com/shitan198u/immich-go-gui)
- Powered by [simulot/immich-go](https://github.com/simulot/immich-go)
