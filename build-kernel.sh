#!/bin/sh
# Build the kernel outside pmbootstrap. This tree expects AOSP/Proton clang
# plus GNU binutils. Alpine clang (LLVM=1) is the wrong compiler.
#
# Full build:
#   ./build-kernel.sh <kernel tree> <clang dir>
# olddefconfig gate only (no clang):
#   PMOS_KERNEL_MODE=config ./build-kernel.sh <kernel tree>
#
# The kernel tree does not need a pmos branch. The fragment is merged here.
set -e
SRC=${1:?kernel source tree}
MODE=${PMOS_KERNEL_MODE:-image}
case "$MODE" in
config|image) ;;
*) echo "PMOS_KERNEL_MODE must be config or image" >&2; exit 1 ;;
esac
if [ "$MODE" = image ]; then
	CLANG_DIR=${2:?toolchain dir containing bin/clang}
	export PATH="$CLANG_DIR/bin:$PATH"
fi
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$HERE/out
mkdir -p "$OUT"
cp "$HERE/linux-infinix-x6525/config-helix-stock.aarch64" "$OUT/.config"
"$SRC/scripts/kconfig/merge_config.sh" -m -O "$OUT" "$OUT/.config" "$HERE/linux-infinix-x6525/pmos.config"
if [ "$MODE" = image ]; then
	make -C "$SRC" O="$OUT" ARCH=arm64 CC=clang LLVM_IAS=1 \
		CROSS_COMPILE=aarch64-linux-gnu- CLANG_TRIPLE=aarch64-linux-gnu- \
		olddefconfig
else
	make -C "$SRC" O="$OUT" ARCH=arm64 olddefconfig
fi

fragment="$HERE/linux-infinix-x6525/pmos.config"
# Drop trailing comments so "CONFIG_FOO=y  # note" still counts.
normalized=$(mktemp)
sed -E 's/[[:space:]]+#.*//; s/[[:space:]]+$//' "$fragment" > "$normalized"
fail=0
# Every CONFIG_FOO=y in the fragment must still be =y.
for sym in $(sed -n 's/^\(CONFIG_[A-Z0-9_]*\)=y$/\1/p' "$normalized"); do
	if ! grep -q "^${sym}=y$" "$OUT/.config"; then
		got=$(grep -E "^${sym}=|^# ${sym} is not set" "$OUT/.config" || true)
		echo "$sym is not =y after olddefconfig (${got:-absent})" >&2
		fail=1
	fi
done
# Every "# CONFIG_FOO is not set" in the fragment must not have been turned back on.
for sym in $(sed -n 's/^# \(CONFIG_[A-Z0-9_]*\) is not set$/\1/p' "$normalized"); do
	if grep -q "^${sym}=y$" "$OUT/.config"; then
		echo "$sym is still =y after olddefconfig" >&2
		fail=1
	fi
done
echo "Resolved fragment options:"
for sym in $(sed -n 's/^\(CONFIG_[A-Z0-9_]*\)=y$/\1/p; s/^# \(CONFIG_[A-Z0-9_]*\) is not set$/\1/p' "$normalized"); do
	grep -E "^${sym}=|^# ${sym} is not set" "$OUT/.config" || echo "$sym absent"
done
rm -f "$normalized"
[ "$fail" = 0 ] || exit 1
if [ "$MODE" = config ]; then
	echo "olddefconfig kept the fragment. Resolved config: $OUT/.config"
	exit 0
fi

make -C "$SRC" O="$OUT" ARCH=arm64 CC=clang LLVM_IAS=1 \
	CROSS_COMPILE=aarch64-linux-gnu- CLANG_TRIPLE=aarch64-linux-gnu- \
	-j"$(nproc)" Image modules
make -C "$SRC" O="$OUT" ARCH=arm64 CC=clang LLVM_IAS=1 \
	CROSS_COMPILE=aarch64-linux-gnu- CLANG_TRIPLE=aarch64-linux-gnu- \
	modules_install INSTALL_MOD_PATH="$OUT/modroot" INSTALL_MOD_STRIP=1
KREL=$(cat "$OUT/include/config/kernel.release")
tar czf "$HERE/linux-infinix-x6525-$KREL.tar.gz" -C "$OUT" arch/arm64/boot/Image .config -C "$OUT/modroot" lib/modules
echo "Built $KREL. Image: $OUT/arch/arm64/boot/Image  (feed it to repack.sh)"
