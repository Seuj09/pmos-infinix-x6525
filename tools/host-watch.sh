#!/bin/sh
# Run on the second phone (the USB host, e.g. a Galaxy A01 Core with an Ubuntu chroot), as root.
#
#   sh host-watch.sh [vid:pid] [host-ip]
#
# It does three things the plain `lsusb` / `ssh` attempt does not:
#   1. logs EVERY USB device that appears or disappears, with a timestamp, so a phone that
#      enumerates under a different id (stock fastboot 18d1:4ee0, Spreadtrum download mode
#      1782:4d00, the pmOS gadget 18d1:d001) is visible instead of "lsusb shows nothing";
#   2. logs the host kernel's own USB lines (dmesg) - "device descriptor read/64, error -71" or
#      "over-current" mean the link came up but is unstable, which is a different bug from
#      "nothing ever attached";
#   3. when the pmOS gadget appears, finds its network interface, gives it an address and tests
#      the initramfs debug shell (telnet, port 23) and SSH (port 22) on 172.16.42.1.
#
# Needs: a POSIX sh, ip, and optionally nc and dmesg. Reads /sys, so /sys must be mounted in the
# chroot (mount --bind /sys <chroot>/sys). Nothing here has been run on an A01 Core yet; the
# logic is exercised against a fake /sys tree by tools/test-host-watch.sh.
VIDPID=${1:-18d1:d001}
HOSTIP=${2:-172.16.42.2}
PEER=${PEER:-172.16.42.1}
SYS=${SYS:-/sys}
INTERVAL=${INTERVAL:-1}
LOOPS=${LOOPS:-0}          # 0 = forever; tests set a count

log() { printf '%s %s\n' "$(date +%H:%M:%S)" "$*"; }

# "vid:pid dir" for each USB device (not interfaces: those have no idVendor)
list_usb() {
	for d in "$SYS"/bus/usb/devices/*; do
		[ -f "$d/idVendor" ] || continue
		printf '%s:%s %s\n' "$(cat "$d/idVendor")" "$(cat "$d/idProduct")" "$d"
	done
}

# first network interface name under a USB device directory
net_of() {
	for n in "$1"/*/net/* "$1"/*/*/net/*; do
		[ -e "$n" ] && { basename "$n"; return 0; }
	done
	return 1
}

port_open() {
	command -v nc >/dev/null 2>&1 || return 2
	nc -z -w 2 "$PEER" "$1" >/dev/null 2>&1
}

configured=""
prev=""
seen_dmesg=0
n=0
log "watching for $VIDPID (any USB change is logged); host address $HOSTIP"
while :; do
	cur=$(list_usb | sort)
	if [ "$cur" != "$prev" ]; then
		# lines only in one of the two lists
		printf '%s\n' "$prev" | sort > "${TMPDIR:-/tmp}/hw.prev.$$"
		printf '%s\n' "$cur" | sort > "${TMPDIR:-/tmp}/hw.cur.$$"
		comm -13 "${TMPDIR:-/tmp}/hw.prev.$$" "${TMPDIR:-/tmp}/hw.cur.$$" |
			while read -r id dir; do [ -n "$id" ] && log "ATTACHED  $id  ($dir)"; done
		comm -23 "${TMPDIR:-/tmp}/hw.prev.$$" "${TMPDIR:-/tmp}/hw.cur.$$" |
			while read -r id dir; do [ -n "$id" ] && log "DETACHED  $id"; done
		rm -f "${TMPDIR:-/tmp}/hw.prev.$$" "${TMPDIR:-/tmp}/hw.cur.$$"
		prev=$cur
		configured=""
	fi

	# host kernel's own view: new USB-related lines since last look
	if command -v dmesg >/dev/null 2>&1; then
		total=$(dmesg 2>/dev/null | wc -l)
		if [ "$total" -gt "$seen_dmesg" ]; then
			dmesg 2>/dev/null | tail -n +"$((seen_dmesg + 1))" |
				grep -i -E 'usb|cdc|ncm|musb|xhci|over-?current|enumerat' |
				while read -r l; do log "dmesg: $l"; done
		fi
		seen_dmesg=$total
	fi

	# the pmOS gadget: bring the network up once per attach
	dir=$(printf '%s\n' "$cur" | awk -v id="$VIDPID" '$1 == id { print $2; exit }')
	if [ -n "$dir" ] && [ -z "$configured" ]; then
		if ifc=$(net_of "$dir"); then
			log "gadget found, interface $ifc: configuring $HOSTIP/24"
			ip link set "$ifc" up 2>&1 | while read -r l; do log "ip: $l"; done
			ip addr add "$HOSTIP/24" dev "$ifc" 2>&1 | while read -r l; do log "ip: $l"; done
			configured=$ifc
			sleep 2
			if port_open 23; then log "telnet 23 open: initramfs debug shell, use: telnet $PEER"
			elif [ $? -eq 2 ]; then log "no nc installed: try telnet $PEER or ssh user@$PEER by hand"
			else log "port 23 closed (debug shell only runs before the rootfs mounts)"; fi
			port_open 22 && log "ssh 22 open: ssh user@$PEER"
		else
			log "gadget $VIDPID is attached but no network interface appeared: the host kernel lacks the driver for this function (check cdc_ncm / cdc_ether) or the function is not NCM"
			configured="noif"
		fi
	fi

	n=$((n + 1))
	[ "$LOOPS" -gt 0 ] && [ "$n" -ge "$LOOPS" ] && break
	sleep "$INTERVAL"
done
