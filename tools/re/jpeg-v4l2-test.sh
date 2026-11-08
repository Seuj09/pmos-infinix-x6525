#!/bin/sh
# Run on the phone (needs v4l-utils and python3 + numpy; or copy the .raw files away and run the
# check on a PC):  sudo sh jpeg-v4l2-test.sh [/dev/videoN]
# Decodes the four test JPEGs through the V4L2 decoder and checks them.
D=$(dirname "$0")/jpeg-test
V=${1:-$(v4l2-ctl --list-devices 2>/dev/null | awk '/sprd-jpg|JPEG decoder/{f=1;next} f&&/\/dev\/video/{print $1;exit}')}
[ -n "$V" ] || { echo "no sprd-jpg video device found; pass it as the first argument"; exit 2; }
run() { # name W H pixfmt
	AH=$((($3 + 15) / 16 * 16)); BPL=$((($2 + 15) / 16 * 16))
	v4l2-ctl -d "$V" --set-fmt-video-out=pixelformat=JPEG \
		--set-fmt-video=width=$2,height=$AH,pixelformat=$4 \
		--stream-mmap=3 --stream-out-mmap=3 --stream-from="$D/$1.jpg" --stream-to=/tmp/$1.raw --stream-count=1 \
		|| { echo "$1: v4l2-ctl failed"; return; }
	python3 "$(dirname "$0")/jpeg-v4l2-check.py" "$D/$1.npz" $2 $3 $4 /tmp/$1.raw && echo "$1 ok" || echo "$1 FAILED"
}
run 444 32 32 NV16
run 422 32 32 NV16
run 420odd 50 38 NV12
run gray 48 24 GREY
# the same image twice in a row: the block must be reset between images
run 422 32 32 NV16
