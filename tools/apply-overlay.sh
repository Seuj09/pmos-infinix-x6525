#!/bin/sh
# Apply the X6525 port (device tree + panel driver + build glue) to a copy of
# the ums9230-mainline kernel tree.
#
#   git clone --depth 1 --branch v7.2-rc6-ums9230-0 \
#       https://codeberg.org/ums9230-mainline/linux kernel
#   ./tools/apply-overlay.sh kernel
#
# It copies dts/ums9230-infinix-x6525.dts, drivers/panel-td4160-hx.c and
# bindings/infinix,td4160-hx-panel.yaml into the tree, then applies
# patches/0001-x6525-build-glue.patch, which adds the dtb-y entry, the panel
# Kconfig and Makefile lines, and the DT binding entries (board compatible and
# vendor prefix). Re-running is safe: a patch that is already in is reported
# rather than applied twice.
#
# The patch is cut against the tag the CI pins. When you bump that tag, refresh
# it: fetch the five touched files at the new tag, re-apply the same edits, and
# re-run `diff -urN a b` - otherwise this script will refuse to run and tell you
# so instead of half-applying something.
set -e

TREE=${1:?usage: apply-overlay.sh <kernel tree>}
HERE=$(cd "$(dirname "$0")/.." && pwd)

command -v git >/dev/null 2>&1 || {
	echo "this script needs git (for 'git apply')" >&2
	exit 1
}

for f in arch/arm64/boot/dts/sprd/ums9230.dtsi \
         drivers/gpu/drm/panel/panel-chipone-icnl9916-720x1600.c; do
	if [ ! -f "$TREE/$f" ]; then
		echo "$TREE does not look like the ums9230 kernel tree ($f missing)" >&2
		exit 1
	fi
done

install -Dm644 "$HERE/dts/ums9230-infinix-x6525.dts" \
	"$TREE/arch/arm64/boot/dts/sprd/ums9230-infinix-x6525.dts"
install -Dm644 "$HERE/drivers/panel-td4160-hx.c" \
	"$TREE/drivers/gpu/drm/panel/panel-td4160-hx.c"
install -Dm644 "$HERE/bindings/infinix,td4160-hx-panel.yaml" \
	"$TREE/Documentation/devicetree/bindings/display/panel/infinix,td4160-hx-panel.yaml"
echo "copied device tree, panel driver and binding"

# 'git apply' rather than patch(1): its --check semantics are unambiguous in
# both directions, whereas patch's reverse detection happily reports success
# after silently ignoring -R.
for p in "$HERE"/patches/*.patch; do
	[ -e "$p" ] || continue
	if git -C "$TREE" apply -R --check "$p" 2>/dev/null; then
		echo "$(basename "$p") is already applied"
	elif git -C "$TREE" apply --check "$p" 2>/dev/null; then
		git -C "$TREE" apply "$p"
		echo "applied $(basename "$p")"
	else
		echo "ERROR: $(basename "$p") does not apply to $TREE" >&2
		echo "Refresh it against the tag you checked out - see the header." >&2
		exit 1
	fi
done

echo "overlay applied to $TREE"
