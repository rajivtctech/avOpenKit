"""Recognise common FFmpeg failures and say what they mean in plain words (spec F7)."""

from __future__ import annotations

import re

from PyQt6.QtCore import QCoreApplication


def translate(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


def explain(log: str) -> str | None:
    """A one-line explanation for a failed job's log, or None when the cause is not recognised."""
    patterns = [
        (r"already exists\. Exiting",
         translate("errors", "A file with the output name already exists, and it was not replaced.")),
        (r"No such file or directory",
         translate("errors", "A file named in the command could not be found.")),
        (r"Permission denied",
         translate("errors", "The output folder cannot be written to, or the file is open in another program.")),
        (r"No space left on device",
         translate("errors", "The disk is full.")),
        (r"Unknown encoder '([^']+)'",
         translate("errors", "This FFmpeg build does not include the encoder the task needs.")),
        (r"No such filter: '([^']+)'",
         translate("errors", "This FFmpeg build does not include a filter the task needs.")),
        (r"Invalid data found when processing input|moov atom not found",
         translate("errors", "The input file is damaged or is not a media file FFmpeg can read.")),
        (r"Could not find tag for codec|codec not currently supported in container|"
         r"Could not write header",
         translate("errors", "The chosen output format cannot hold this kind of audio or video without converting it.")),
        (r"height not divisible by 2|width not divisible by 2",
         translate("errors", "The picture size must be an even number of pixels for this encoder.")),
        (r"Unable to (open|find a suitable output format)",
         translate("errors", "FFmpeg could not work out the output format from the file name.")),
    ]
    for pattern, message in patterns:
        if re.search(pattern, log):
            return message
    return None
