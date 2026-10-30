#!/bin/sh
# One read-only report for the four open features: the 90 Hz refresh, the Wi-Fi hotspot (AP mode),
# Bluetooth, and cellular. It changes nothing (no power-on, no hotspot start, no modem poke), so it
# is safe to run at any time, over SSH or on the phone's terminal:
#   sh tools/diag-features.sh        # writes /var/tmp/features-diag.txt; send that file
# The GPU section runs tools/check-gpu.sh, so fetch both files into the same folder.
OUT=/var/tmp/features-diag.txt
# Write as we go: a hang or reboot must not lose what was already collected.
exec > "$OUT" 2>&1
echo "started $(date)"
S=; [ "$(id -u)" = 0 ] || S=sudo
have() { command -v "$1" >/dev/null 2>&1; }
{
echo "== 0. build"; uname -r; apk info -v linux-postmarketos-unisoc-ums9230 device-infinix-x6525 2>/dev/null

echo; echo "== 1. display refresh (60 vs 90 Hz)"
for c in /sys/class/drm/card*-DSI*; do
	[ -e "$c" ] || continue
	echo "-- $(basename "$c")  status=$(cat "$c/status" 2>/dev/null)"
	echo "   modes: $(tr '\n' ' ' < "$c/modes" 2>/dev/null)"
done
[ -e /sys/class/drm ] || echo "no /sys/class/drm"
have wlr-randr && timeout 5 wlr-randr 2>&1 | head -12
$S dmesg | grep -iE 'dsi|td4160|modeset|mode.*(set|fail)|refresh' | tail -20

echo; echo "== 2. Wi-Fi hotspot (AP mode)"
have iw && { echo "-- supported interface modes:"; timeout 5 iw list 2>/dev/null | sed -n '/Supported interface modes/,/^\s*$/p' | head -10; }
have nmcli && timeout 5 nmcli -f DEVICE,TYPE,STATE device 2>&1 | head -8
have dnsmasq && echo "dnsmasq: $(command -v dnsmasq)" || echo "dnsmasq: NOT installed (NetworkManager shared mode needs it)"
$S dmesg | grep -iE 'sc23xx|wlan.*(ap|beacon|mode|fail)|start_ap|wifi.*fail' | tail -15

echo; echo "== 3. Bluetooth"
have bluetoothctl && timeout 5 $S bluetoothctl show 2>&1 | head -12
have hciconfig && timeout 5 $S hciconfig -a 2>&1 | head -8
have rfkill && timeout 5 $S rfkill list bluetooth 2>&1 || echo "rfkill: not installed"
$S dmesg | grep -iE 'bluetooth|btsprd|hci0|bd ?address|local-bd|random|pskey|opcode' | tail -20
echo "-- address source (prodnv file, /var/lib file, device-tree property):"
ls -l /var/lib/x6525/ 2>&1 | tail -n +2
ls -l /dev/disk/by-partlabel/prodnv 2>&1
$S cat /proc/device-tree/soc/bluetooth*/local-bd-address 2>/dev/null | od -An -tx1 | head -1

echo; echo "== 4. cellular"
ls -l /lib/firmware/sprd/l_*.bin 2>&1
timeout 5 systemctl status x6525-modem-nv --no-pager 2>&1 | head -8
$S dmesg | grep -iE 'sprd_modem|remoteproc|pubcp|modem' | tail -25
echo "-- remoteproc state:"; for r in /sys/class/remoteproc/*; do [ -e "$r" ] && echo "$(basename "$r"): $(cat "$r/name" 2>/dev/null) $(cat "$r/state" 2>/dev/null)"; done
echo "-- rpmsg channels (names decide whether rpmsg_wwan can bind):"; ls /sys/bus/rpmsg/devices/ 2>&1
echo "-- tty/wwan nodes:"; for n in /dev/ttyS* /dev/ttyBT* /dev/ttyUSB* /dev/ttyACM* /dev/*wwan*; do [ -e "$n" ] && printf '%s ' "$n"; done; echo
if have mmcli; then timeout 5 $S mmcli -L 2>&1 | head -5; else echo "ModemManager (mmcli): not installed"; fi

echo; echo "== 5. GPU acceleration (tools/check-gpu.sh, next to this script)"
D=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
if [ -f "$D/check-gpu.sh" ]; then
	sh "$D/check-gpu.sh" 2>&1
else
	echo "check-gpu.sh not found next to this script. Fetch it too:"
	echo "  curl -fsSL https://raw.githubusercontent.com/Seuj09/pmos-infinix-x6525/main/tools/check-gpu.sh -o /tmp/check-gpu.sh && sh /tmp/check-gpu.sh"
fi

echo; echo "== 6. Camera (tools/check-camera.sh, next to this script)"
if [ -f "$D/check-camera.sh" ]; then
	sh "$D/check-camera.sh" 2>&1
else
	echo "check-camera.sh not found next to this script."
fi

echo; echo "== 7. services"
timeout 5 systemctl --failed --no-pager 2>&1 | head -8
}
echo "finished $(date); wrote $OUT ($(wc -l < "$OUT") lines): please send it"
