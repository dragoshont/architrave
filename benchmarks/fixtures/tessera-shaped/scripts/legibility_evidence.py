import json
from pathlib import Path
import struct
import sys
import zlib


root = Path(__file__).resolve().parents[1]
surface = sys.argv[1]


def write_png(path: Path) -> None:
    raw = b"\x00\x00\x00\x00\xff\xff\xff"

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


if surface == "web":
    (root / "runtime/web-dom.json").write_text('{"role":"main"}\n')
    (root / "runtime/web-a11y.json").write_text('{"violations":[]}\n')
    write_png(root / "runtime/web.png")
    print(json.dumps({
        "url": "http://fixture.invalid/release",
        "domSnapshot": "runtime/web-dom.json",
        "accessibilityTree": "runtime/web-a11y.json",
        "screenshot": "runtime/web.png",
        "workflowPassed": True,
        "consoleErrors": [],
        "networkFailures": [],
    }))
elif surface == "electron":
    write_png(root / "runtime/electron.png")
    print(json.dumps({
        "windowCount": 1,
        "route": "/release",
        "screenshot": "runtime/electron.png",
        "workflowPassed": True,
        "crashed": False,
        "consoleErrors": [],
        "ipcErrors": [],
    }))
elif surface == "ios":
    write_png(root / "runtime/ios.png")
    print(json.dumps({
        "bundleId": "example.architrave.fixture",
        "installed": True,
        "launched": True,
        "terminated": True,
        "relaunched": True,
        "navigationPassed": True,
        "crashed": False,
        "screenshot": "runtime/ios.png",
    }))
elif surface in {"electron-screenshot", "ios-screenshot"}:
    name = surface.split("-", 1)[0]
    write_png(root / f"runtime/{name}.png")
    print(f"runtime/{name}.png")
else:
    raise SystemExit(f"unknown surface: {surface}")