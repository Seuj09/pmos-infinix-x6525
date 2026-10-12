#!/bin/sh
# Build the kernel OUTSIDE pmbootstrap with the toolchain the tree expects (AOSP/Proton clang + GNU binutils).
# Alpine's clang (LLVM=1) is the wrong compiler for this tree. Untested: adjust CLANG_DIR to your toolchain.
# Usage: ./build-kernel.sh /path/to/android_kernel_ums9230 /path/to/clang   (kernel tree on the `pmos` branch)
set -e
SRC=${1:?kernel source tree}; CLANG_DIR=${2:?toolchain dir containing bin/clang}
HERE=$(cd "$(dirname "$0")" && pwd)
export PATH="$CLANG_DIR/bin:$PATH"
OUT=$HERE/out; mkdir -p "$OUT"
cp "$HERE/linux-infinix-x6525/config-helix-stock.aarch64" "$OUT/.config"
"$SRC/scripts/kconfig/merge_config.sh" -m -O "$OUT" "$OUT/.config" "$HERE/linux-infinix-x6525/pmos.config"
MK="make -C $SRC O=$OUT ARCH=arm64 CC=clang LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu- CLANG_TRIPLE=aarch64-linux-gnu-"
$MK olddefconfig
# Fail loudly if olddefconfig dropped a symbol the first boot depends on.
for s in DEVTMPFS FHANDLE MMC_SDHCI_SPRD SPRD_USBPINMUX SPRD_USB_CONFIGFS_RNDIS DRM_SPRD; do
  grep -q "^CONFIG_$s=y" "$OUT/.config" || { echo "CONFIG_$s is not =y after olddefconfig" >&2; exit 1; }
done
$MK -j"$(nproc)" Image modules
$MK modules_install INSTALL_MOD_PATH="$OUT/modroot" INSTALL_MOD_STRIP=1
KREL=$(cat "$OUT/include/config/kernel.release")
tar czf "$HERE/linux-infinix-x6525-$KREL.tar.gz" -C "$OUT" arch/arm64/boot/Image .config -C "$OUT/modroot" lib/modules
echo "Built $KREL. Image: $OUT/arch/arm64/boot/Image  (feed it to repack.sh)"
