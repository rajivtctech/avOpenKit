"""The guided tasks (spec section 3), in the order they are listed in the window."""

from . import (audio, convert, crop, export, gif, join, rotate, sequence, sheet, shrink, speed,
               subtitles, trim)

ALL = [trim, shrink, convert, audio, join, rotate, gif, subtitles,
       crop, sequence, sheet, speed, export]
