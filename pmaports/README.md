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

2. **The panel driver must be enabled in that package's config.** The ums9230 config has
   `CONFIG_DRM_PANEL_CHIPONE_ICNL9916_720_1600=y` (built-in, not a module — the display has to work in
   the initramfs for unl0kr). Add the same for ours:

   ```
   CONFIG_DRM_PANEL_TD4160_HX=y
   ```

   Its dependencies (`DRM_MIPI_DSI`, `BACKLIGHT_CLASS_DEVICE`, `DRM_SPRD`) are already `=y` there.

3. **A `u-boot-infinix-x6525` package.** The deviceinfo chainloads U-Boot from `boot_a`, so without it
   nothing boots. That needs a board in the [U-Boot fork](https://codeberg.org/ums9230-mainline/u-boot),
   which does not exist yet — the same shape as `u-boot-jolla-c2` (`configs/reeder-s19mps_defconfig`,
   plus a device tree). The X6525 needs the SDHCI/eMMC path, which that fork already has (the reeder
   exercises UFS).

Then, before opening the MR:

- create the wiki page and list the device under "booting" on the Devices page — CI runs
  `.ci/lib/check_devices_in_wiki.py` and fails without it;
- commit titles follow `COMMITSTYLE.md`: `device-infinix-x6525: …`;
- keep it in `device/testing/` initially, like `device-jolla-c2`.

Later (not boot-blocking): a `firmware-infinix-x6525-wcn` package for WiFi/Bluetooth, a touch driver
(Omnivision TCM over SPI) with its module listed in a `modules-initfs` file, and the Awinic AW32257
charger.
