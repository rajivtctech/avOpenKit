"""The eight guided tasks (spec section 3), in the order they are listed in the window."""

from . import audio, convert, gif, join, rotate, shrink, subtitles, trim

ALL = [trim, shrink, convert, audio, join, rotate, gif, subtitles]
