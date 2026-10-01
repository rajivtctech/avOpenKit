#!/bin/bash
# Design trial: run the command each task T1-T8 would generate against generated clips and
# check the result with ffprobe. Run from the project folder: bash trials/commands_trial.sh
set -u
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT; cd "$W"
F="ffmpeg -v error -nostdin -y"
dur(){ ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }
vc(){ ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$1"; }
ac(){ ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$1"; }
ok(){ printf '%-28s %s\n' "$1" "$2"; }

mk(){ $F -f lavfi -i "testsrc2=size=1280x720:rate=30:duration=$2" -f lavfi -i "sine=frequency=$3:duration=$2" \
      -c:v libx264 -preset veryfast -g 60 -keyint_min 60 -sc_threshold 0 -pix_fmt yuv420p -c:a aac "$1"; }
mk "in a'b.mp4" 20 440; mk b.mp4 6 880          # first name has a space and a quote (N3)
IN="in a'b.mp4"
printf '1\n00:00:01,000 --> 00:00:04,000\nHello\n\n2\n00:00:05,000 --> 00:00:08,000\nनमस्ते\n' > s.srt

# T1 trim
$F -ss 3.5 -to 9 -i "$IN" -map 0 -c copy -avoid_negative_ts make_zero t1fast.mp4
ok "T1 fast (ask 3.5-9 = 5.5 s)" "got $(dur t1fast.mp4) s, video $(vc t1fast.mp4) (copied)"
$F -ss 3.5 -to 9 -i "$IN" -c:v libx264 -crf 18 -preset veryfast -c:a aac t1exact.mp4
ok "T1 exact" "got $(dur t1exact.mp4) s"

# T2 shrink to 2 MB: video kbit/s = size*8/duration - audio, less 3 % overhead margin
TARGET_KB=2000; D=20; A=96
V=$(python3 -c "print(int(($TARGET_KB*8*0.97)/$D - $A))")
$F -i "$IN" -c:v libx264 -b:v ${V}k -preset veryfast -pass 1 -passlogfile p -an -f null /dev/null
$F -i "$IN" -c:v libx264 -b:v ${V}k -preset veryfast -pass 2 -passlogfile p -c:a aac -b:a ${A}k t2.mp4
ok "T2 shrink to ${TARGET_KB} kB" "video ${V}k -> $(( $(stat -c %s t2.mp4) / 1000 )) kB"

# T3 convert
$F -i "$IN" -map 0 -c copy t3.mkv;                     ok "T3 mp4->mkv copy" "$(vc t3.mkv)/$(ac t3.mkv)"
$F -i "$IN" -t 4 -c:v libvpx-vp9 -crf 34 -b:v 0 -deadline realtime -cpu-used 8 -c:a libopus t3.webm
ok "T3 mp4->webm" "$(vc t3.webm)/$(ac t3.webm)"

# T4 extract audio
$F -i "$IN" -vn -c:a copy t4.m4a;                      ok "T4 keep original" "$(ac t4.m4a), $(dur t4.m4a) s"
$F -i "$IN" -vn -c:a libmp3lame -q:a 2 t4.mp3;         ok "T4 mp3" "$(ac t4.mp3)"

# T5 join without re-encoding (concat demuxer; list file quotes each path)
python3 - "$IN" b.mp4 > list.txt <<'PY'
import sys
for p in sys.argv[1:]:
    print("file '" + p.replace("'", "'\\''") + "'")
PY
$F -f concat -safe 0 -i list.txt -map 0 -c copy t5.mp4;  ok "T5 join 20 s + 6 s" "got $(dur t5.mp4) s"

# T6 rotation metadata, no re-encode
for a in 90 -90 180; do
  $F -display_rotation $a -i "$IN" -map 0 -c copy t6.mp4
  ok "T6 -display_rotation $a" "ffprobe rotation $(ffprobe -v error -select_streams v:0 -show_entries stream_side_data=rotation -of csv=p=0 t6.mp4)"
done
$F -i "$IN" -t 3 -vf transpose=1 -c:v libx264 -preset veryfast -c:a copy t6b.mp4
ok "T6 bake in transpose=1" "$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 t6b.mp4)"

# T7 GIF, palette built and used in one command
$F -ss 2 -t 3 -i "$IN" -vf "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" t7.gif
ok "T7 gif 3 s 480 px 12 fps" "$(( $(stat -c %s t7.gif) / 1000 )) kB, $(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 t7.gif) frames"

# T8 subtitles
$F -i "$IN" -t 9 -vf "subtitles=s.srt" -c:v libx264 -preset veryfast -c:a copy t8burn.mp4
ok "T8 burn in" "$(vc t8burn.mp4), $(dur t8burn.mp4) s"
$F -i "$IN" -i s.srt -map 0 -map 1 -c copy -c:s mov_text t8soft.mp4
ok "T8 add as track (mp4)" "subtitle stream: $(ffprobe -v error -select_streams s:0 -show_entries stream=codec_name -of csv=p=0 t8soft.mp4)"

# F5 progress output
ffmpeg -v error -nostdin -y -progress pipe:1 -nostats -i "$IN" -t 5 -c:v libx264 -preset veryfast -an prog.mp4 > prog.txt
ok "F5 -progress keys" "$(cut -d= -f1 prog.txt | sort -u | tr '\n' ' ')"
ok "F5 last block" "$(tail -3 prog.txt | tr '\n' ' ')"
