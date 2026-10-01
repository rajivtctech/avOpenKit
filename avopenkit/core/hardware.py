"""Hardware H.264 encoders (spec F14).

FFmpeg lists every encoder it was built with, whether or not this machine has the chip and
driver for it. An encoder is offered only after a short test encode with it has succeeded,
using the same arguments a real job would use.
"""

from __future__ import annotations

import glob
import sys
from dataclasses import dataclass

from .ffmpeg import Tools, run_quiet


@dataclass(frozen=True)
class HwEncoder:
    id: str             # "vaapi", "qsv", "nvenc", "amf"
    encoder: str        # FFmpeg's encoder name
    label: str          # shown to the user
    device: str = ""    # VAAPI render node

    def global_args(self) -> list[str]:
        """Arguments that go before the inputs."""
        return ["-vaapi_device", self.device] if self.id == "vaapi" else []

    def filter_tail(self) -> str:
        """Filters that must end the video filter chain, to hand frames to the encoder."""
        return {"vaapi": "format=nv12,hwupload", "qsv": "format=nv12", "nvenc": "format=yuv420p",
                "amf": "format=nv12"}[self.id]

    def codec_args(self, quality: int) -> list[str]:
        """Encoder and quality. `quality` is the CRF the software encoder would use; hardware
        encoders have their own scales, so the same number is only roughly the same quality."""
        q = str(quality)
        knobs = {"vaapi": ["-qp", q], "qsv": ["-global_quality", q],
                 "nvenc": ["-rc", "vbr", "-cq", q, "-b:v", "0"],
                 "amf": ["-rc", "cqp", "-qp_i", q, "-qp_p", q]}[self.id]
        return ["-c:v", self.encoder, *knobs]


LABELS = {
    "vaapi": "VAAPI - Intel or AMD graphics",
    "qsv": "Intel Quick Sync",
    "nvenc": "NVIDIA NVENC",
    "amf": "AMD AMF",
}


def candidates(tools: Tools) -> list[HwEncoder]:
    """Encoders this FFmpeg build has that could exist on this kind of system. Not yet tested."""
    found = []
    if sys.platform.startswith("linux") and tools.has_encoder("h264_vaapi"):
        for node in sorted(glob.glob("/dev/dri/renderD*")):
            found.append(HwEncoder("vaapi", "h264_vaapi", LABELS["vaapi"], node))
    for ident, name in (("qsv", "h264_qsv"), ("nvenc", "h264_nvenc"), ("amf", "h264_amf")):
        if tools.has_encoder(name):
            found.append(HwEncoder(ident, name, LABELS[ident]))
    return found


def test_args(hw: HwEncoder) -> list[str]:
    """A quarter-second encode of a test pattern, with a scale filter as real jobs may have."""
    return ["-v", "error", "-nostdin", *hw.global_args(),
            "-f", "lavfi", "-i", "testsrc2=size=256x144:rate=10:duration=0.3",
            "-vf", f"scale=128:-2,{hw.filter_tail()}", *hw.codec_args(23), "-f", "null", "-"]


def works(tools: Tools, hw: HwEncoder) -> bool:
    try:
        return run_quiet([tools.ffmpeg, *test_args(hw)], timeout=20).returncode == 0
    except Exception:           # a driver that hangs or crashes is simply "not working"
        return False


def detect(tools: Tools) -> list[HwEncoder]:
    """Hardware encoders that work here, one per kind (the first render node that works)."""
    working: dict[str, HwEncoder] = {}
    for hw in candidates(tools):
        if hw.id not in working and works(tools, hw):
            working[hw.id] = hw
    return list(working.values())


def find(tools: Tools, ident: str) -> HwEncoder | None:
    """The working encoder of one kind, or None. Tests only that kind."""
    for hw in candidates(tools):
        if hw.id == ident and works(tools, hw):
            return hw
    return None
