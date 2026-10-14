# pmos-infinix-x6525

Draft postmarketOS port for the Infinix X6525 (Unisoc UMS9230 / T606, downstream 5.4 kernel).
**Untested.** See `NOTES.md` for what was extracted from the stock boot/vendor_boot/dtbo images,
`linux-infinix-x6525/pmos.config` for the kernel config changes, and `repack.sh` for a manual first-boot test.

The kernel config check runs on GitHub Actions. Open the Actions tab, choose **kernel**, and run the workflow. Mode `config` stops after `olddefconfig`. Mode `image` also builds the Image.

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

`.github/workflows/build.yml` does the same on every push that touches those directories: it clones the
pinned tag, checks that the submission series applies to it and reproduces `dts/`, `drivers/` and
`bindings/`, applies the overlay, builds `ums9230-infinix-x6525.dtb`, enables `DRM_SPRD`,
`DRM_PANEL_TD4160_HX`, `TOUCHSCREEN_OVT_TCM_SPI`, `CHARGER_BQ2415X` and `CHARGER_EXTCON_DETECT`
behind an olddefconfig gate, and compiles the three drivers. The `uboot` job builds the board and
uploads `x6525-uboot`; the kernel job uploads `x6525-build`.

## What is where

| Path | What |
|---|---|
| `dts/`, `drivers/` | the device tree and the three drivers (panel, touch, charger) to send upstream |
| `bindings/` | new DT bindings (the board/vendor entries are in `patches/`) |
| `patches/` | build glue for the pinned kernel tag: kernel tree entries, the panel/touchscreen/charger Kconfig and Makefile entries, and the gpio binding fix |
| `patches/upstream/` | the nine `git am`-able patches for submission, plus notes on where each goes |
| `uboot/` | the X6525 U-Boot board: a defconfig and a device tree, no board directory |
| `patches/upstream-uboot/` | the two U-Boot board patches for submission |
| `pmaports/` | the `device-infinix-x6525` package, mirroring the pmaports path |
| `firmware/` | the touch HDL image off the device, the upload tarball and its hashes |
| `tools/` | dtbo/dtb extraction, the live device-tree dumper, the HDL image checker and the vendor-sequence converter |
| `linux-infinix-x6525/`, `device-infinix-x6525/`, `repack.sh` | the earlier downstream 5.4 approach |


First boot of the mainline port, stage by stage with what to send back: [FIRST_BOOT.md](FIRST_BOOT.md).

To collect the remaining hardware facts from the stock system in one go: `sh tools/collect-live.sh` (see `NOTES.md`, "Next steps").
