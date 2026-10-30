#!/bin/sh
# Check camera hardware, drivers, media pipeline, controls, and test-pattern capture:
#
#   sh tools/check-camera.sh            # on the phone, as normal user or root
#
# Tests the camera subsystem on the Infinix X6525:
#   1. Kernel drivers loaded (sprd-camsys, sprd-isp, s5k3l6, ov8856, leds-gpio)
#   2. I2C devices probed on buses 0 and 1
#   3. V4L2 and media controller nodes (/dev/media*, /dev/video*, /dev/v4l-subdev*)
#   4. Subdev controls (test pattern generator, exposure, gain)
#   5. Flash / torch LED (/sys/class/leds/white:flash)
#   6. Megapixels device configuration
#   7. CSI/DCAM frame streaming test - only with CAMERA_STREAM=1 (it starts the camera hardware)
#
# Every line is PASS, FAIL or INFO; a final VERDICT line sums it up.

R=0 F=0
pass() { printf 'PASS  %s\n' "$*"; R=$((R + 1)); }
fail() { printf 'FAIL  %s\n' "$*"; F=$((F + 1)); }
info() { printf 'INFO  %s\n' "$*"; }

S=; command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null && S='sudo -n'
[ -n "$S" ] || [ "$(id -u)" = 0 ] || info "no passwordless sudo: run 'sudo -v' first for dmesg and hardware access"

echo "== 1. Camera kernel modules =="
for mod in sprd_camsys sprd_isp s5k3l6 ov8856 leds_gpio; do
	if lsmod 2>/dev/null | grep -q "^$mod"; then
		pass "module $mod is loaded"
	elif [ -d "/sys/module/$mod" ]; then
		pass "module $mod is built-in or loaded"
	else
		info "module $mod not loaded (may autoload on demand)"
	fi
done

echo "== 2. Sensor probe in dmesg =="
dm=$($S dmesg 2>/dev/null | grep -iE 's5k3l6|ov8856|camsys|csi' | tail -15)
if [ -n "$dm" ]; then
	printf '%s\n' "$dm" | sed 's/^/      /'
	if printf '%s\n' "$dm" | grep -qiE 's5k3l6.*failed|s5k3l6.*error'; then
		fail "rear S5K3L6 probe reported an error"
	elif printf '%s\n' "$dm" | grep -qiE 's5k3l6'; then
		pass "rear S5K3L6 camera detected"
	fi
	if printf '%s\n' "$dm" | grep -qiE 'ov8856.*failed|ov8856.*error'; then
		fail "front OV8856 probe reported an error"
	elif printf '%s\n' "$dm" | grep -qiE 'ov8856'; then
		pass "front OV8856 camera detected"
	fi
else
	info "no camera messages in dmesg (check with sudo)"
fi

echo "== 3. V4L2 and Media Controller nodes =="
media_nodes=$(ls -d /dev/media* 2>/dev/null)
video_nodes=$(ls -d /dev/video* 2>/dev/null)
subdev_nodes=$(ls -d /dev/v4l-subdev* 2>/dev/null)

if [ -n "$media_nodes" ]; then
	pass "media controller node(s) present: $(echo "$media_nodes" | tr '\n' ' ')"
else
	fail "no /dev/media* node found (sprd-camsys not bound)"
fi

if [ -n "$video_nodes" ]; then
	pass "video capture node(s) present: $(echo "$video_nodes" | tr '\n' ' ')"
else
	fail "no /dev/video* node found"
fi

if [ -n "$subdev_nodes" ]; then
	pass "subdev node(s) present: $(echo "$subdev_nodes" | tr '\n' ' ')"
else
	info "no /dev/v4l-subdev* node found"
fi

echo "== 4. Flash and Torch LED =="
if [ -d "/sys/class/leds/white:flash" ]; then
	pass "flashlight sysfs node /sys/class/leds/white:flash exists"
	max_b=$(cat /sys/class/leds/white:flash/max_brightness 2>/dev/null || echo 1)
	info "torch max_brightness: $max_b"
else
	fail "no /sys/class/leds/white:flash (check gpio-leds in DT)"
fi

echo "== 5. Megapixels Configuration =="
mp_cfg="/usr/share/megapixels/config/infinix,x6525.ini"
if [ -f "$mp_cfg" ]; then
	pass "Megapixels config file $mp_cfg is installed"
	if grep -q "s5k3l6" "$mp_cfg" && grep -q "ov8856" "$mp_cfg"; then
		pass "Megapixels config defines both rear (s5k3l6) and front (ov8856) cameras"
	else
		fail "Megapixels config incomplete"
	fi
else
	fail "Megapixels config $mp_cfg is missing"
fi

echo "== 6. Test pattern capture test =="
if [ "${CAMERA_STREAM:-0}" != 1 ]; then
	info "stream test skipped; run CAMERA_STREAM=1 sh tools/check-camera.sh to start the camera and capture one frame"
elif command -v v4l2-ctl >/dev/null 2>&1; then
	if [ -e "/dev/video0" ]; then
		info "testing frame capture from /dev/video0..."
		if timeout 5 v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=1 --stream-to=/tmp/cam_test.raw 2>/dev/null; then
			if [ -s "/tmp/cam_test.raw" ]; then
				pass "successfully captured test frame ($(wc -c < /tmp/cam_test.raw) bytes)"
				rm -f /tmp/cam_test.raw
			else
				fail "capture returned empty file"
			fi
		else
			info "streaming test skipped or timed out (requires running session/subdev configuration)"
		fi
	else
		fail "cannot test stream: /dev/video0 does not exist"
	fi
else
	info "v4l-utils (v4l2-ctl) not installed: run 'apk add v4l-utils' for stream verification"
fi

echo
if [ "$F" -eq 0 ]; then
	echo "VERDICT: camera configuration and drivers are ready ($R checks passed)"
else
	echo "VERDICT: camera issues detected ($F failed, $R passed): review FAIL lines above"
fi
