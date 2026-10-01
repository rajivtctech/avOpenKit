#!/bin/bash
# Design trial for the artist tasks T9-T13: run the command each would generate against
# generated clips and check the result with ffprobe. bash trials/artist_tasks_trial.sh
set -u
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT; cd "$W"
F="ffmpeg -v error -nostdin -y"
dim(){ ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$1"; }
dur(){ ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }
vc(){ ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt,profile -of csv=p=0 "$1"; }
ac(){ ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$1"; }
nf(){ ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$1"; }
ok(){ printf '%-34s %s\n' "$1" "$2"; }
$F -f lavfi -i "testsrc2=size=1280x720:rate=30:duration=12" -f lavfi -i "sine=frequency=440:duration=12" \
   -c:v libx264 -preset veryfast -g 60 -pix_fmt yuv420p -c:a aac in.mp4

# T9 crop: 1280x720 -> square 720x720 from the centre; 9:16 -> 404x720 (even); 4:5 -> 576x720
$F -i in.mp4 -vf "crop=720:720:280:0" -c:v libx264 -crf 18 -preset veryfast -c:a copy t9sq.mp4;   ok "T9 square, centre" "$(dim t9sq.mp4) audio $(ac t9sq.mp4)"
$F -i in.mp4 -vf "crop=404:720:438:0" -c:v libx264 -crf 18 -preset veryfast -c:a copy t9v.mp4;    ok "T9 9:16, centre" "$(dim t9v.mp4)"
$F -display_rotation 90 -i in.mp4 -c copy rot.mp4
$F -i rot.mp4 -vf "crop=720:720:0:280" -c:v libx264 -crf 18 -preset veryfast -c:a copy t9r.mp4;   ok "T9 on a rotated file (720x1280)" "$(dim t9r.mp4) rotation '$(ffprobe -v error -select_streams v:0 -show_entries stream_side_data=rotation -of csv=p=0 t9r.mp4)'"

# T10 video -> images, every frame and 2 per second; images -> video
mkdir all two
$F -i in.mp4 -t 2 -fps_mode passthrough all/frame-%05d.png;                 ok "T10 every frame of 2 s (60)" "$(ls all | wc -l) files, first $(ls all | head -1)"
$F -i in.mp4 -vf fps=2 -q:v 2 two/frame-%05d.jpg;                           ok "T10 2 per second of 12 s (24)" "$(ls two | wc -l) files"
$F -framerate 24 -start_number 1 -i all/frame-%05d.png -c:v libx264 -crf 18 -preset veryfast -pix_fmt yuv420p t10.mp4
ok "T10 60 images at 24 fps (2.5 s)" "$(dur t10.mp4) s, $(nf t10.mp4) frames, $(vc t10.mp4)"
mkdir "odd %dir" && cp all/frame-0000[1-9].png "odd %dir/"
$F -framerate 10 -start_number 1 -i "odd %%dir/frame-%05d.png" -c:v libx264 -pix_fmt yuv420p pct.mp4 && ok "T10 a %% in the folder name" "$(nf pct.mp4) frames (written as %%%%)"

# T11 contact sheet: 4x3 = 12 frames, each from its own seek, first frame only
ARGS=(); G=""; P=""
for i in $(seq 0 11); do t=$(python3 -c "print(f'{12*($i+0.5)/12:.3f}')"); ARGS+=(-ss "$t" -i in.mp4); G+="[$i:v:0]trim=end_frame=1,scale=320:-2,setsar=1[v$i];"; P+="[v$i]"; done
SECONDS=0
$F "${ARGS[@]}" -filter_complex "${G}${P}concat=n=12:v=1:a=0,tile=4x3:padding=6:margin=6:color=black[s]" -map "[s]" -frames:v 1 -q:v 2 t11.jpg
ok "T11 4x3 sheet, 320 px tiles" "$(dim t11.jpg) in ${SECONDS}s (expect 1310x566)"
SECONDS=0
$F -i in.mp4 -vf "fps=12/12,scale=320:-2,tile=4x3" -frames:v 1 -q:v 2 t11b.jpg; ok "T11 same by decoding everything" "$(dim t11b.jpg) in ${SECONDS}s"

# T12 speed: 2x with sound, 8x silent, half speed with sound, quarter speed (atempo chained)
$F -i in.mp4 -vf "setpts=PTS/2" -af "atempo=2" -c:v libx264 -crf 18 -preset veryfast -c:a aac t12a.mp4;  ok "T12 2x (12 -> 6 s)" "$(dur t12a.mp4) s, audio $(ac t12a.mp4)"
$F -i in.mp4 -vf "setpts=PTS/8" -an -c:v libx264 -crf 18 -preset veryfast t12b.mp4;                      ok "T12 8x silent (1.5 s)" "$(dur t12b.mp4) s, audio '$(ac t12b.mp4)'"
$F -i in.mp4 -t 4 -vf "setpts=PTS/0.5" -af "atempo=0.5" -c:v libx264 -crf 18 -preset veryfast -c:a aac t12c.mp4; ok "T12 half speed of 4 s (8 s)" "$(dur t12c.mp4) s"
$F -i in.mp4 -t 2 -vf "setpts=PTS/0.25" -af "atempo=0.5,atempo=0.5" -c:v libx264 -crf 18 -preset veryfast -c:a aac t12d.mp4; ok "T12 quarter speed of 2 s (8 s)" "$(dur t12d.mp4) s"
$F -i in.mp4 -t 2 -af "atempo=0.25" -vn q.m4a 2>&1 | head -1; ok "T12 atempo=0.25 alone" "$(dur q.m4a 2>/dev/null) s (works unchained if 8)"
$F -i in.mp4 -af "atempo=8" -vn e.m4a 2>&1 | head -1; ok "T12 atempo=8 alone" "$(dur e.m4a 2>/dev/null) s (1.5 if accepted)"

# T13 ProRes for editing
for p in 0 1 2 3; do $F -i in.mp4 -t 2 -map 0:v:0 -map 0:a? -c:v prores_ks -profile:v $p -pix_fmt yuv422p10le -c:a pcm_s16le t13_$p.mov; ok "T13 ProRes profile $p" "$(vc t13_$p.mov), audio $(ac t13_$p.mov), $(( $(stat -c %s t13_$p.mov) / 1000 )) kB for 2 s"; done
ok "source for comparison" "$(( $(stat -c %s in.mp4) / 1000 )) kB for 12 s"
ffmpeg -hide_banner -h encoder=prores_ks 2>/dev/null | grep -E '^\s+-(profile|vendor)' | head -3
