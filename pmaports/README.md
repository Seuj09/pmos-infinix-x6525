# pmaports-side device package

`device/testing/device-infinix-x6525/` mirrors the pmaports path, so it can be copied straight into a
pmaports checkout. It is modelled on `device-jolla-c2` (same SoC, same boot chain), with the modern
deviceinfo only — no `kernel_cmdline`, no `modules_initfs`, both of which `deviceinfo_schema.toml`
marks `fate = "obsolete"`.

**It cannot be submitted as-is.** Three things must exist first, in this order:

1. **The DTS and drivers must reach the kernel package.** pmaports builds
   `linux-postmarketos-unisoc-ums9230` from a *tarball at a tag*, so `deviceinfo_dtb` cannot resolve
   until a tree at that tag contains `sprd/ums9230-infinix-x6525.dtb`. Two routes, and the first
   works today: `device/testing/linux-postmarketos-unisoc-ums9230/` here is that package with the
   ten patches from `../patches/upstream/` added to `source=` - `default_prepare`, which the package
   already calls, applies them with `patch -p1`, verified against the same tag it builds from - plus
   the five config symbols below. Copy it in beside the device package and the ROM builds. Once the
   series is merged instead, drop that directory, bump `KERNEL_TAG` in
   `../.github/workflows/build.yml` and the `_tag` in the kernel APKBUILD to a tag containing it, and
   the patches come back out.

2. **Five config symbols in that package's config.** Its config
   (`config-postmarketos-unisoc-ums9230.aarch64`) is what the ROM's kernel actually uses, and it
   already carries everything else this port needs: the PMIC chain (`SPI_SPRD_ADI`,
   `MFD_SC27XX_PMIC`, `REGULATOR_SC2730`), `SC27XX_ADC`, `GENERIC_ADC_THERMAL`, `FUEL_GAUGE_SC27XX`,
   `EXTCON_USB_GPIO`, `CHARGER_MANAGER`, `DRM_SPRD`, and MUSB (`USB_MUSB_HDRC`/`USB_MUSB_SPRD` — the
   blocker from the old downstream plan). Only these five are missing, and the staging package above
   has them:

   ```
   CONFIG_DRM_PANEL_TD4160_HX=y       # the sibling panel is =y too, for unl0kr
   CONFIG_TOUCHSCREEN_OVT_TCM_SPI=m   # as is the sibling touch driver
   CONFIG_CHARGER_EXTCON_DETECT=m
   CONFIG_CHARGER_BQ2415X=m           # the file had this one explicitly "is not set"
   CONFIG_SERIAL_SPRD=y               # the UART in stdout-path, inert without it
   ```

   Three things learned the hard way, worth keeping: a symbol whose dependency is off is a no-op, so
   `SC27XX_ADC` without `MFD_SC27XX_PMIC` is silently switched back off by `olddefconfig` (that is
   how the CI gate failed once — the tree's own `defconfig` still has none of the PMIC chain, which
   is why the gate enables it by hand); the thermistor zones are named
   `board-thermal`/`pa-thermal`/`chg-thermal` because `thermal-zones.yaml` only accepts
   `<name>-thermal`; and `REGULATOR_SC2730` matters early rather than late, since
   `vddemmccore`/`vddsdio` are its LDOs and the rootfs is on that eMMC.

   Charging and the battery indicator come up when those modules load, which is after the rootfs
   mounts. Touch *in* the initramfs (unl0kr) would additionally need the touch module and the HDL
   image in a `modules-initfs` file — this device package has none yet, which is fine for a first
   boot on USB networking.

3. **A `u-boot-infinix-x6525` package.** The deviceinfo chainloads U-Boot from `boot_a`, so without it
   nothing boots. The package is complete, and it builds from the port's own fork of the U-Boot tree -
   branch `x6525` in `ums9230-mainline-u-boot`, which is that fork's `ums9230` plus the two board
   commits this repo carries in `../uboot/` and `../patches/upstream-uboot/` - so it waits on nothing.
   `_commit` and the `sha512` are the fork's tip; point both back at `codeberg.org/ums9230-mainline/u-boot`
   once the board is merged there. The X6525 boots from eMMC on `sdio3`, which U-Boot's SDHCI path
   covers (the reeder exercises UFS instead), and CI builds `u-boot.bin` from the same two files on
   every push.

## The touch firmware

`firmware-infinix-x6525` is complete and fetchable: its `source=` is the tarball in `../firmware/`,
served from this repository pinned to the commit that added it, and the port's CI fetches that URL and
checks it against the package's sha512 on every push. `.github/workflows/firmware-release.yml` can put
a versioned copy on this repository's releases — it runs only when someone presses **Run workflow**,
never on a push, and it checks the tarball three ways first (it must rebuild byte for byte from
`hdl_firmware_01.img`, match the APKBUILD's sha512, and pass `tools/check-hdl-image.py`) — but nothing
depends on it, because the package already works.

The image is `proprietary` vendor firmware, which is why the device package only *recommends* this
package: a ROM built without it boots and simply has no touchscreen.

Then, before opening the MR:

- create the wiki page and list the device under "booting" on the Devices page — CI runs
  `.ci/lib/check_devices_in_wiki.py` and fails without it;
- commit titles follow `COMMITSTYLE.md`: `device-infinix-x6525: …`;
- keep it in `device/testing/` initially, like `device-jolla-c2`.

Later (not boot-blocking): a `firmware-infinix-x6525-wcn` package for WiFi/Bluetooth, the touch
driver's module in a `modules-initfs` file, and what charging is still missing. The touch driver and
its firmware package draft exist now - note that touch in the initramfs (unl0kr) would need both the
module and the HDL image there, not just the module. Charging itself is wired up (mainline's bq2415x
drives the AW32257, which is a bq24158); what is left is BC1.2 detection so it can tell a wall charger
from a PC and go above the 500 mA ceiling, the `board-thmzone` thermal zone the vendor nodes point at,
and an `otg-vbus` regulator, which the bq2415x driver does not provide.
