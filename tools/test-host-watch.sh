#!/bin/sh
# Exercise tools/host-watch.sh against a fake /sys tree with stub ip, nc and dmesg.
# Usage: sh tools/test-host-watch.sh   (exit 0 = every check passed)
here=$(cd "$(dirname "$0")" && pwd)
t=$(mktemp -d) || exit 1
trap 'rm -rf "$t"' EXIT
mkdir -p "$t/bin" "$t/sys/bus/usb/devices"
cat > "$t/bin/ip" <<'S'
#!/bin/sh
echo "STUB ip $*" >> "$STUBLOG"
S
cat > "$t/bin/nc" <<'S'
#!/bin/sh
for a; do p=$a; done
[ "$p" = 23 ]
S
cat > "$t/bin/dmesg" <<'S'
#!/bin/sh
printf 'unrelated line\nusb 1-1: device descriptor read/64, error -71\n'
S
chmod +x "$t/bin/"*
export PATH="$t/bin:$PATH" STUBLOG="$t/stub.log" SYS="$t/sys" LOOPS=2 INTERVAL=0 TMPDIR="$t"
dev() { # name vid pid [netif]
	d="$t/sys/bus/usb/devices/$1"; mkdir -p "$d"
	echo "$2" > "$d/idVendor"; echo "$3" > "$d/idProduct"
	[ -n "$4" ] && mkdir -p "$d/$1:1.0/net/$4"
}
fail=0
check() { # description, pattern, file
	if grep -q -E "$2" "$3"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi
}
out="$t/out"

sh "$here/host-watch.sh" > "$out" 2>&1
check "starts and watches" "watching for 18d1:d001" "$out"

dev 1-1 18d1 4ee0
sh "$here/host-watch.sh" > "$out" 2>&1
check "logs a non-target device (stock fastboot)" "ATTACHED  18d1:4ee0" "$out"
check "relays host dmesg usb error" "dmesg: .*error -71" "$out"
if grep -q "unrelated line" "$out"; then echo "FAIL dmesg filter"; fail=1; else echo "ok   dmesg filter drops unrelated lines"; fi
if grep -q "configuring" "$out"; then echo "FAIL configured a non-target device"; fail=1; else echo "ok   does not configure a non-target device"; fi

rm -rf "$t/sys/bus/usb/devices/1-1"
dev 1-2 18d1 d001
sh "$here/host-watch.sh" > "$out" 2>&1
check "gadget without interface is reported" "no network interface appeared" "$out"

rm -rf "$t/sys/bus/usb/devices/1-2"
dev 1-2 18d1 d001 usb1
: > "$t/stub.log"
sh "$here/host-watch.sh" 18d1:d001 172.16.42.9 > "$out" 2>&1
check "gadget with interface is configured" "interface usb1: configuring 172.16.42.9/24" "$out"
check "ip link up called" "STUB ip link set usb1 up" "$t/stub.log"
check "ip addr add called" "STUB ip addr add 172.16.42.9/24 dev usb1" "$t/stub.log"
check "debug shell port detected" "telnet 23 open" "$out"
exit $fail
