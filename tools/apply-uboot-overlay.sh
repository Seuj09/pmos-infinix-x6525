#!/bin/sh
# Apply the X6525 U-Boot board (defconfig + device tree) to a copy of the
# ums9230-mainline U-Boot fork.
#
#   git clone --depth 1 --branch ums9230 \
#       https://codeberg.org/ums9230-mainline/u-boot
#   ./tools/apply-uboot-overlay.sh uboot
#
# Unlike the kernel side this needs no patch: a U-Boot board for this SoC is
# only a defconfig plus a device tree, with no Kconfig or Makefile changes,
# because SYS_BOARD and SYS_CONFIG_NAME already default to "ums9230" for
# TARGET_UMS9230. The two files are copied to the paths they live at in the fork.
set -e

TREE=${1:?usage: apply-uboot-overlay.sh <u-boot tree>}
HERE=$(cd "$(dirname "$0")/.." && pwd)

for f in arch/arm/dts/ums9230.dtsi arch/arm/mach-sprd/Kconfig; do
	if [ ! -f "$TREE/$f" ]; then
		echo "$TREE does not look like the ums9230 U-Boot fork ($f missing)" >&2
		exit 1
	fi
done

install -Dm644 "$HERE/uboot/dts/ums9230-infinix-x6525.dts" \
	"$TREE/arch/arm/dts/ums9230-infinix-x6525.dts"
install -Dm644 "$HERE/uboot/configs/infinix-x6525_defconfig" \
	"$TREE/configs/infinix-x6525_defconfig"

echo "board applied to $TREE"
