"""The User Guide must not drift from the program."""

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "USER_GUIDE.md"
sys.path.insert(0, str(ROOT / "tools"))
import make_guide_assets  # noqa: E402


@pytest.fixture(scope="module")
def guide():
    return GUIDE.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="the guide shows commands as typed on Linux")
def test_command_reference_is_what_the_program_generates(guide):
    """Part 7.3 is produced by the task modules. If this fails, run:
       .venv/bin/python tools/make_guide_assets.py reference"""
    start = guide.index(make_guide_assets.BEGIN) + len(make_guide_assets.BEGIN)
    end = guide.index(make_guide_assets.END)
    assert guide[start:end].strip() == make_guide_assets.command_reference().strip()


@pytest.mark.skipif(sys.platform == "win32", reason="the guide is generated on Linux")
def test_command_reference_does_not_depend_on_where_it_is_generated(guide, tmp_path, monkeypatch):
    """No path from the machine that built the guide may appear in it."""
    here = make_guide_assets.command_reference()
    monkeypatch.chdir(tmp_path)
    assert make_guide_assets.command_reference() == here
    assert str(Path.home()) not in guide


def test_every_task_has_commands_in_the_reference():
    reference = make_guide_assets.command_reference()
    for heading in ("Trim", "Shrink to a size", "Convert format", "Extract audio", "Join clips",
                    "Fix rotation", "Make a GIF", "Subtitles", "Crop to a shape",
                    "Image sequence", "Contact sheet", "Change speed", "Export for editing"):
        assert f"### {heading}\n" in reference
    assert reference.count("```") >= 50 and "h264_vaapi" in reference


def ui_strings():
    """Every string constant in the window's source, as the parser joins them."""
    found = set()
    for path in (ROOT / "avopenkit").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value.replace("&", ""))
    return found


def test_every_button_and_label_the_guide_quotes_exists_in_the_program(guide):
    """The guide writes the exact words on the screen as **"..."**."""
    strings = ui_strings()
    quoted = set(re.findall(r'\*\*"([^"\n]+)"', guide)) | set(re.findall(r'"([^"\n]+)"\*\*', guide))
    assert len(quoted) > 80
    missing = sorted(q for q in quoted if not any(q in s for s in strings))
    assert not missing, f"quoted in the guide but not found in the program: {missing}"


def test_every_figure_exists(guide):
    figures = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", guide)
    assert len(figures) == 8
    for name in figures:
        assert (GUIDE.parent / name).is_file(), name


def test_messages_the_guide_explains_are_the_program_s_messages(guide):
    strings = ui_strings()
    section = guide[guide.index("## 6.1 Messages in the note box"):guide.index("## 6.3 Common puzzles")]
    rows = re.findall(r"^\| ([^|]+?) \|", section, re.M)
    messages = [r for r in rows if r not in ("Message", "---") and not r.startswith("-")]
    assert len(messages) > 20
    def known(message):
        # "…" in the guide stands for the part that varies (a number, a name).
        pieces = [p.strip(" .") for p in re.split(r"…|\(or [^)]*\)", message) if len(p.strip(" .")) > 8]
        return pieces and all(any(piece in s for s in strings) for piece in pieces)
    missing = [m for m in messages if not known(m)]
    assert not missing, f"explained in the guide but not produced by the program: {missing}"


def test_guide_states_the_version_it_describes(guide):
    from avopenkit import __version__
    assert f"For version {__version__}" in guide and f"version {__version__} as it actually behaves" in guide
