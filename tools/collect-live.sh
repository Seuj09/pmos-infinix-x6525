#!/bin/sh
# Collect, in one go, what the running stock system knows about the hardware this port
# still has to describe. Run it in a root shell on the phone and send back the output file:
#
#     sh tools/collect-live.sh            # writes ./x6525-live.txt
#     sh tools/collect-live.sh out.txt
#
# It only reads: /proc/device-tree, sysfs, /proc, debugfs (if mounted) and dmesg. Anything it
# cannot read is noted and skipped, so a partial file is still useful. Needs root for debugfs
# and dmesg; python3 is used for the device-tree dump (tools/dtdir-dump.py) when present.
#
# What each section is for:
#   compatible list   - every device the stock tree describes, to spot what is not ported yet
#   thermal           - the board-thmzone / thermistor tables (charge policy, thermal zones)
#   gpio              - the state of ap_gpio 115 (charge-pd) and the panel/touch lines
#   regulators        - supplies and their current voltages (the DTS vddusb33/vddsdio/... names)
#   i2c / spi / input - what is on each bus and which driver bound to it
#   wifi / bt / audio - the chips, so the right firmware package can be named
#   power_supply      - every attribute of every supply, the reference for the charger work
OUT=${1:-x6525-live.txt}
HERE=$(cd "$(dirname "$0")" && pwd)
# /proc/device-tree is a symlink; find does not descend into a symlinked start point, which is
# why an earlier run of this script came back with an empty compatible list.
DT=$(readlink -f /proc/device-tree 2>/dev/null)
[ -d "$DT" ] || DT=/proc/device-tree
: > "$OUT"

sec() { printf '\n===== %s =====\n' "$1" >> "$OUT"; }
run() { # run <label> <command...>
	sec "$1"; shift
	"$@" >> "$OUT" 2>&1 || echo "(failed: $*)" >> "$OUT"
}
cat_if() { sec "$1"; if [ -r "$1" ]; then cat "$1" >> "$OUT" 2>&1; else echo "(cannot read $1)" >> "$OUT"; fi; }

sec "identity"
{
	date
	uname -a
	getprop ro.product.model 2>/dev/null
	getprop ro.product.device 2>/dev/null
	getprop ro.boot.hardware 2>/dev/null
} >> "$OUT" 2>&1
cat_if /proc/cmdline

# every compatible string with its node path: the one list that shows all described hardware
sec "device tree: every node's compatible"
find "$DT/" -name compatible 2>/dev/null | sort | while read -r f; do
	printf '%s: ' "${f#$DT}" >> "$OUT"
	tr '\0' ' ' < "$f" >> "$OUT" 2>/dev/null
	echo >> "$OUT"
done

dump_node() { # dump_node <path-under-/proc/device-tree>
	sec "device tree: $1"
	if [ ! -e "$DT/$1" ]; then echo "(absent)" >> "$OUT"; return; fi
	if command -v python3 >/dev/null 2>&1 && [ -f "$HERE/dtdir-dump.py" ]; then
		python3 -I "$HERE/dtdir-dump.py" -R "$DT/$1" >> "$OUT" 2>&1
	else
		find "$DT/$1" -type f 2>/dev/null | while read -r p; do
			printf '%s = ' "${p#$DT}" >> "$OUT"
			od -An -tx1 "$p" | tr -d '\n' >> "$OUT"; echo >> "$OUT"
		done
	fi
}
dump_node thermal-zones
dump_node battery
dump_node charger-manager
dump_node tran_charger
dump_node regulators

# each zone's thermal-sensors points at a sensor node by phandle: resolve every distinct one
sec "device tree: thermal sensors behind the zones (resolved by phandle)"
seen=" "
for z in "$DT"/thermal-zones/*/thermal-sensors; do
	[ -f "$z" ] || continue
	ph=$(od -An -tx1 -N4 "$z" | tr -d ' \n')
	case "$seen" in *" $ph "*) continue ;; esac
	seen="$seen$ph "
	find "$DT/" -name phandle 2>/dev/null | while read -r f; do
		[ "$(od -An -tx1 -N4 "$f" | tr -d ' \n')" = "$ph" ] || continue
		n=$(dirname "$f"); n=${n#$DT/}
		echo "phandle 0x$ph = /$n" >> "$OUT"
		dump_node "$n"
		break
	done
done

# thermistors and the PMIC ADC wherever the stock tree puts them
for n in $(find "$DT/" -name 'thermal-sensor*' -o -name '*thermistor*' 2>/dev/null | sed "s|^$DT/||"); do
	dump_node "$n"
done

sec "thermal: zones as the kernel sees them"
for z in /sys/class/thermal/thermal_zone*; do
	[ -d "$z" ] || continue
	printf '%s type=%s temp=%s\n' "$z" "$(cat $z/type 2>/dev/null)" "$(cat $z/temp 2>/dev/null)" >> "$OUT"
done

sec "gpio (debugfs)"
if [ -r /sys/kernel/debug/gpio ]; then
	cat /sys/kernel/debug/gpio >> "$OUT" 2>&1
else
	mount -t debugfs none /sys/kernel/debug 2>/dev/null
	[ -r /sys/kernel/debug/gpio ] && cat /sys/kernel/debug/gpio >> "$OUT" 2>&1 \
		|| echo "(debugfs gpio not readable - run as root)" >> "$OUT"
fi

sec "regulators"
for r in /sys/class/regulator/regulator.*; do
	[ -d "$r" ] || continue
	printf '%s name=%s uV=%s state=%s\n' "${r##*/}" "$(cat $r/name 2>/dev/null)" \
		"$(cat $r/microvolts 2>/dev/null)" "$(cat $r/state 2>/dev/null)" >> "$OUT"
done

sec "i2c devices"
for d in /sys/bus/i2c/devices/*; do
	[ -e "$d" ] || continue
	printf '%s name=%s driver=%s\n' "${d##*/}" "$(cat $d/name 2>/dev/null)" \
		"$(basename "$(readlink $d/driver 2>/dev/null)" 2>/dev/null)" >> "$OUT"
done
sec "spi devices"
for d in /sys/bus/spi/devices/*; do
	[ -e "$d" ] || continue
	printf '%s driver=%s\n' "${d##*/}" "$(basename "$(readlink $d/driver 2>/dev/null)" 2>/dev/null)" >> "$OUT"
done
sec "input devices"
cat /proc/bus/input/devices >> "$OUT" 2>&1
sec "iio devices"
for d in /sys/bus/iio/devices/*; do
	[ -e "$d" ] || continue
	printf '%s name=%s\n' "${d##*/}" "$(cat $d/name 2>/dev/null)" >> "$OUT"
done

sec "leds / vibrator"
ls /sys/class/leds /sys/class/timed_output >> "$OUT" 2>&1

sec "loaded modules"
cat /proc/modules 2>/dev/null | awk '{print $1}' | sort >> "$OUT"

sec "network interfaces and wireless"
ls /sys/class/net >> "$OUT" 2>&1
ls /sys/class/ieee80211 /sys/class/bluetooth >> "$OUT" 2>&1

sec "audio"
cat /proc/asound/cards >> "$OUT" 2>&1
cat /proc/asound/devices >> "$OUT" 2>&1

sec "cameras (video4linux and dt sensors)"
for v in /sys/class/video4linux/*; do
	[ -e "$v" ] && printf '%s name=%s\n' "${v##*/}" "$(cat $v/name 2>/dev/null)" >> "$OUT"
done

sec "power_supply: every attribute"
for s in /sys/class/power_supply/*; do
	[ -d "$s" ] || continue
	echo "--- ${s##*/}" >> "$OUT"
	for a in "$s"/*; do
		[ -f "$a" ] && [ -r "$a" ] || continue
		printf '%s=%s\n' "${a##*/}" "$(head -c 200 $a 2>/dev/null | tr '\n' ' ')" >> "$OUT"
	done
done

sec "dmesg: the parts that matter for the port"
dmesg 2>/dev/null | grep -iE 'success to request|hdl_firmware|bq24|aw32257|lcd_name|panel|sc27|thermal|merlion|audio.*codec|fingerprint|nfc' | grep -viE 'WCN BASE|WCN SDIO|beacon|sprdwl|touch_report|charger-manager|fgu@' | tail -200 >> "$OUT" 2>&1

sec "pstore / ramoops"
ls -l /sys/fs/pstore >> "$OUT" 2>&1

echo "wrote $OUT ($(wc -c < "$OUT") bytes)"
