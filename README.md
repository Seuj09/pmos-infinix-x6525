# pmos-infinix-x6525

Draft postmarketOS port for the Infinix X6525 (Unisoc UMS9230 / T606): the **mainline** kernel
(`ums9230-mainline`), with a U-Boot board chainloaded from `boot_a`. **Untested** - nothing in this
repository has run on the hardware yet.

[FIRST_BOOT.md](FIRST_BOOT.md) is the port stage by stage, with what to send back at each one, and
how to build the image either here or on GitHub. `NOTES.md` is the record behind it: every value
taken from the stock system or from the running device's own device tree, with its source.

An earlier attempt used the stock 5.4 "Helix" kernel instead. Its files (`linux-infinix-x6525/`,
`device-infinix-x6525/`, `build-kernel.sh`, `repack.sh`) are kept for reference; nothing in the
mainline port uses them, and the workflow that built that kernel has been removed.

## What runs by itself

| Workflow | When | What it does |
|---|---|---|
| `build.yml` | every push touching `dts/`, `drivers/`, `bindings/`, `patches/`, `uboot/`, `tools/` or `pmaports/` | the gate: the submission series applies to the pinned kernel tag and reproduces `dts/`, `drivers/` and `bindings/`; the DTB and the three bindings validate; the drivers compile; the U-Boot and firmware URLs still hash to their APKBUILDs; and the ROM's own kernel config keeps this port's symbols |
| `rom.yml` | Actions → **rom** → *Run workflow* | builds the kernel, U-Boot and rootfs on an arm64 runner and uploads what to flash |
| `firmware-release.yml` | Actions → **firmware release** → *Run workflow* | publishes a versioned copy of the touch firmware to this repository's releases; nothing depends on it |

## vendor_boot and the DTB (corrected)

An earlier version of these notes claimed that `deviceinfo_header_version="4"` makes pmbootstrap write a
vendor_boot without the DTB, so boot had to be flashed alone with `repack.sh`. That is wrong:

- boot-deploy (run by mkinitfs) builds **both** boot.img and vendor_boot.img for header v3/v4, and passes
  `--dtb` from `deviceinfo_dtb` to mkbootimg. A generated vendor_boot therefore does carry a DTB — the one
  from the kernel package. `deviceinfo_flash_offset_*` are not used at v4.
- `device-jolla-c2`, which runs on the same SoC, takes the other route: `--header_version 4` is passed only
  through `deviceinfo_bootimg_custom_args`, with `deviceinfo_header_version` left unset, so pmbootstrap never
  generates or flashes a vendor_boot at all — U-Boot, chainloaded from boot.img, supplies the DTB via its
  extlinux config.

`repack.sh` is a manual fallback, not a requirement.

## Building the mainline port

The device tree, the three drivers and the binding glue live here and are applied to a checkout of the
ums9230-mainline kernel with one script:

```sh
git clone --depth 1 --branch v7.2-rc6-ums9230-0 \
    https://codeberg.org/ums9230-mainline/linux kernel
./tools/apply-overlay.sh kernel
```

That installs `dts/`, the three drivers (`panel-td4160-hx.c`, `ovt-tcm-spi.c`,
`extcon-charger-detect.c`) and the three bindings, then applies `patches/*.patch`: the dtb-y entry, the
board compatible and vendor prefix, and the panel, touchscreen and charger Kconfig/Makefile glue. The
script is idempotent and refuses to half-apply a patch that no longer fits — refresh `patches/` when
you bump the pinned tag.

`.github/workflows/build.yml` does the same on every push that touches those directories, and then
some: it clones the pinned tag, checks that the submission series applies to it and reproduces `dts/`,
`drivers/` and `bindings/`, applies the overlay, builds `ums9230-infinix-x6525.dtb`, validates the
bindings and this board's nodes, enables `DRM_SPRD`, `DRM_PANEL_TD4160_HX`, `TOUCHSCREEN_OVT_TCM_SPI`,
`CHARGER_BQ2415X`, `CHARGER_EXTCON_DETECT` and the PMIC chain the thermistors need behind an
`olddefconfig` gate, compiles the three drivers, refetches the U-Boot archive and the firmware tarball
and compares them against the sha512s in their APKBUILDs, and checks this port's four symbols survive
in the **pmaports** kernel config — the one the ROM is actually built with. The `build` job uploads
`x6525-build`; the `uboot` job builds the board and uploads `x6525-uboot`.

## What is where

| Path | What |
|---|---|
| `dts/`, `drivers/` | the device tree and the three drivers (panel, touch, charger) to send upstream |
| `bindings/` | new DT bindings (the board/vendor entries are in `patches/`) |
| `patches/` | build glue for the pinned kernel tag: kernel tree entries, the panel/touchscreen/charger Kconfig and Makefile entries, and the gpio binding fix |
| `patches/upstream/` | the ten `git am`-able patches for submission, plus notes on where each goes |
| `uboot/` | the X6525 U-Boot board: a defconfig and a device tree, no board directory |
| `patches/upstream-uboot/` | the two U-Boot board patches for submission |
| `pmaports/` | the four packages to copy into pmaports: the device, the kernel (this port's nine patches and its config), U-Boot, and the touch firmware |
| `firmware/` | the touch HDL image off the device, the upload tarball and its hashes |
| `tools/` | dtbo/dtb extraction, the live device-tree dumper, the HDL image checker and the vendor-sequence converter |
| `linux-infinix-x6525/`, `device-infinix-x6525/`, `build-kernel.sh`, `repack.sh` | the earlier downstream 5.4 approach, kept for reference |

First boot of the mainline port, stage by stage with what to send back: [FIRST_BOOT.md](FIRST_BOOT.md).

To collect the remaining hardware facts from the stock system in one go: `sh tools/collect-live.sh` (see `NOTES.md`, "Next steps").
