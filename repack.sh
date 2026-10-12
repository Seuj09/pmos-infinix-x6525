#!/bin/sh
# Manual first-boot test: keep the stock vendor_boot (it carries the DTB) and only swap kernel + ramdisk.
# Needs mkbootimg.py from AOSP (platform/system/tools/mkbootimg). Untested on the device.
set -e
KERNEL=${1:?path to Image}; RAMDISK=${2:?path to initramfs}
mkbootimg.py --header_version 4 --os_version 13.0.0 --os_patch_level 2025-10 \
  --kernel "$KERNEL" --ramdisk "$RAMDISK" \
  --cmdline "androidboot.selinux=permissive enforcing=0 cgroup_disable=pressure,net_prio cgroup_no_v1=cpu,cpuset,blkio,io,memory" \
  -o boot-pmos.img
echo "fastboot flash boot_a boot-pmos.img   # keep a backup of the original boot_a first"
