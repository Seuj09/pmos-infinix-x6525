#!/bin/sh
# Log what the touch path does while you turn the screen off and on with the power button,
# for when no second device is available to run commands over SSH. It only reads.
#
#   1. On the phone's terminal, while touch still works:   sudo sh tools/touch-test.sh
#      (it goes to the background and prints "started" at once)
#   2. Within ~20 s: press the power button (screen off), wait 3 s, press it again (screen on).
#   3. Touch the screen now (it may not respond) for about a minute: swipe, tap, repeat.
#   4. After 2 minutes it has stopped. Reboot (a long power press is fine), then:
#        cat /var/tmp/touch-test.txt
#      and send that file. Every line is synced to disk, so a forced reboot loses nothing.
#
# One line every 2 s: time, touch events from the input device in that window (bytes read from
# /dev/input/eventN: more than 0 means the kernel got events while you touched), the touch
# interrupt count, the panel connector and backlight state, whether phoc is running.
OUT=/var/tmp/touch-test.txt
if [ "$1" != run ]; then
	[ "$(id -u)" = 0 ] || { echo "run as root: sudo sh $0"; exit 1; }
	nohup sh "$0" run >/dev/null 2>&1 &
	echo "started: press the power button off and on within 20 s, then touch the screen for a minute"
	exit 0
fi

# the touch controller's event node
EV=$(awk '/^N: Name=/{n=tolower($0)} /^H: Handlers=/{ if (n ~ /ovt|tcm|touch/) { for(i=1;i<=NF;i++) if ($i ~ /^event[0-9]+$/) { print "/dev/input/" $i; exit } } }' /proc/bus/input/devices)
{
	echo "started $(date +%T); touch device: ${EV:-NOT FOUND}"
	echo "kernel: $(uname -r)"
} > "$OUT"
sync
last=
i=0
while [ "$i" -lt 60 ]; do
	b=0
	[ -n "$EV" ] && b=$(timeout 2 cat "$EV" 2>/dev/null | wc -c)
	irq=$(grep -iE 'ovt|tcm|touch' /proc/interrupts | awk '{s=0; for(k=2;k<=NF;k++) if ($k ~ /^[0-9]+$/) s+=$k; print s}' | head -1)
	drm=
	for c in /sys/class/drm/card*-DSI*; do
		[ -e "$c" ] && drm="$drm $(basename "$c")=$(cat "$c/status" 2>/dev/null)/$(cat "$c/enabled" 2>/dev/null)"
	done
	bl=
	for c in /sys/class/backlight/*; do
		[ -e "$c" ] && bl="$bl $(cat "$c/brightness" 2>/dev/null)/bl_power=$(cat "$c/bl_power" 2>/dev/null)"
	done
	phoc=no; pgrep -x phoc >/dev/null 2>&1 && phoc=yes
	echo "$(date +%T) events=${b}B irq=${irq:-?} drm:${drm:- none} backlight:${bl:- none} phoc=$phoc" >> "$OUT"
	# new kernel lines about touch, panel, suspend
	cur=$(dmesg 2>/dev/null | grep -iE 'ovt|tcm|PM:|suspend|resume|panel|dsi|panfrost' | tail -4)
	if [ "$cur" != "$last" ]; then
		printf '%s\n' "$cur" | sed 's/^/    k: /' >> "$OUT"
		last=$cur
	fi
	sync
	i=$((i + 1))
done
echo "finished $(date +%T)" >> "$OUT"
sync
