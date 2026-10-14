# pmaports-side device package

`device/testing/device-infinix-x6525/` mirrors the pmaports path, so it can be copied straight into a
pmaports checkout. It is modelled on `device-jolla-c2` (same SoC, same boot chain), with the modern
deviceinfo only — no `kernel_cmdline`, no `modules_initfs`, both of which `deviceinfo_schema.toml`
marks `fate = "obsolete"`.

**It cannot be submitted as-is.** Three things must exist first, in this order:

1. **The DTS and driver must be in the kernel tree.** pmaports builds
   `linux-postmarketos-unisoc-ums9230` from a *tarball at a tag*, so `deviceinfo_dtb` cannot resolve
   until the tree at that tag contains `sprd/ums9230-infinix-x6525.dtb`. Feed it the series in
   `../patches/upstream/`, then bump `KERNEL_TAG` in `../.github/workflows/build.yml` and the `_tag`
   in the pmaports kernel APKBUILD to a tag that includes it.

2. **The port's drivers must be enabled in that package's config.** The ums9230 config has
   `CONFIG_DRM_PANEL_CHIPONE_ICNL9916_720_1600=y` (built-in, not a module — the display has to work in
   the initramfs for unl0kr). Add ours:

   ```
   CONFIG_DRM_PANEL_TD4160_HX=y
   CONFIG_TOUCHSCREEN_OVT_TCM_SPI=m
   CONFIG_CHARGER_BQ2415X=y
   CONFIG_FUEL_GAUGE_SC27XX=y
   CONFIG_CHARGER_EXTCON_DETECT=y
   CONFIG_EXTCON_USB_GPIO=y
   ```

   The panel's dependencies (`DRM_MIPI_DSI`, `BACKLIGHT_CLASS_DEVICE`, `DRM_SPRD`) are already `=y`
   there. The charger four are what the DTS nodes bind to and **nothing enables them today**: the
   pinned tree's own `defconfig` has none of `CHARGER_BQ2415X`, `CHARGER_EXTCON_DETECT`,
   `FUEL_GAUGE_SC27XX` or `CHARGER_MANAGER`, and CI turns them on only for its own build (the
   `olddefconfig` gate in the workflow). They can be modules, but then charging and the battery
   indicator only come up after the rootfs mounts. Touch can be a module too — for touch *in* the
   initramfs (unl0kr) that module and the HDL image both have to go in a `modules-initfs` file.

3. **A `u-boot-infinix-x6525` package.** The deviceinfo chainloads U-Boot from `boot_a`, so without it
   nothing boots. The board itself is drafted in `../uboot/` and `../patches/upstream-uboot/`; the
   package draft here mirrors `u-boot-jolla-c2` and has three things to fill in once the board is
   upstreamed to the fork: `_commit`, `pkgver` and the tarball's `sha512sum`. The X6525 boots from
   eMMC on `sdio3`, which U-Boot's SDHCI path covers (the reeder exercises UFS instead), and CI already
   builds `u-boot.bin` from these files.

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
