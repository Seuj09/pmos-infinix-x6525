#!/bin/sh
# Load the out-of-tree Trusty modules in dependency order and show what appeared.
set -e
D=$(dirname "$0")
for m in trusty trusty-irq trusty-virtio trusty-ipc trusty-log; do
	echo "== insmod $m =="
	sudo insmod "$D/$m.ko"
done
ls -l /dev/trusty-ipc-dev0 2>/dev/null || true
dmesg | grep -iE 'trusty|tipc' | tail -40
