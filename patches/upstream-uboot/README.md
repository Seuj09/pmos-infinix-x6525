# U-Boot board patches

Two patches for [codeberg.org/ums9230-mainline/u-boot](https://codeberg.org/ums9230-mainline/u-boot),
split the way that fork splits its own board commits (`WIP: add device tree …` and
`configs: Add defconfig …`). Verified to apply to a clean clone of the `ums9230` branch and to
reproduce byte-identical files to what CI builds.

```sh
git clone --depth 1 --branch ums9230 https://codeberg.org/ums9230-mainline/u-boot
git -C u-boot am "$PWD"/patches/upstream-uboot/0*.patch
```

`tools/apply-uboot-overlay.sh` does the same without `git am`, which is what CI uses (the build is
`make ARCH=arm infinix-x6525_defconfig && make ARCH=arm`, natively — the fork's mach-sprd selects
ARM64 for `TARGET_UMS9230`, which is why the pmaports package is `pmb:cross-native`).

Where it goes: the fork first (Codeberg PR), then mainline U-Boot by mail (`u-boot@lists.denx.de`) once
the SoC support itself lands there. Same rule as the kernel patches: read them and own them before
submitting — Codeberg restricts LLM-generated contributions.

## Untested on hardware

First things to check when it runs:

- whether eMMC comes up on `sdio3` — the reeder boots from UFS, so that path is less exercised. The
  microSD slot is enabled as a rescue route for exactly this reason.
- the memory size, copied from the reeder; this board reports `androidboot.ddrsize=4096M`.
- `CONFIG_SYS_BOOTM_LEN=0x800000` (8 MB, also copied) — worth watching if the uncompressed arm64
  `Image` on the boot partition ever exceeds it.

## Deliberately not included

No `board/` directory and no Kconfig or Makefile change: `SYS_BOARD` and `SYS_CONFIG_NAME` already
default to `ums9230` for `TARGET_UMS9230`. UFS/SCSI are dropped from the defconfig because this board
has no UFS device.
