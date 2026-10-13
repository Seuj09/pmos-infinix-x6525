# Facts extracted from your files
- boot.img: header v4, page 4096, os A13 patch 2025-10, kernel = 5.4.302-Helix arm64 Image (EFI stub), no AVB footer
- vendor_boot.img: header v4, kernel_addr 0x8000, ramdisk_addr 0x5400000, tags 0x100, dtb_addr 0x1f00000,
  cmdline "console=ttyS1,115200n8 androidboot.selinux=permissive enforcing=0"
  ramdisk table: [0] platform 2.2 MB (only first_stage_ramdisk, no .ko), [1] "recovery" 45 MB
  DTB section: container with 1 FDT, model "Spreadtrum UMS9230 1H10 SoC", compatible sprd,ums9230
- dtb_a: all zeros, so the DTB comes from vendor_boot
- dtbo.img: 21 entries, bootloader picks idx 18 (androidboot.dtbo_idx=18): "UMS9230-1H10-GO Board",
  with panel variants lcd_td4160_hx / lcd_td4160_txd / lcd_ft8057s_dpt and touch (focaltech/omnivision)
- Panel and touch are chosen by the bootloader from the cmdline (lcd_name=lcd_td4160_hx_mipi_hdp_x6525, tp_vendor_id=0x130)

# Confirmed on the running device (root shell)
- `lcd_name=lcd_td4160_hx_mipi_hdp_x6525` -> the panel is the TD4160 **HX** variant, 720x1612
- Touch is **Omnivision TCM over SPI**: bound driver `omnivision_tcm_spi` on `spi3.0`, input device
  `omnivision_tcm_touch`. The vendor also loads `focaltech_ft8722`, `focaltech_ft8756_spi_ts` and
  `nvt_nt36xxx_spi_ts` as candidates; himax and chipone are absent, so the loaded-module list alone
  does not identify the part - the bound driver does.
- The SC27xx PMIC is on `spi4.0`; a Goodix fingerprint device registers `gf-keys`.
- Internal storage (UFS vs eMMC) is still undetermined - check the board DTB.
- The `lcd_*` group on the cmdline is `lcd_id` / `lcd_name` / `tp_vendor_id` / `lcd_base` / `lcd_size` /
  `logo_bpix` - it carries **no timing values** (the paste was truncated at the very end, so a stray
  parameter cannot be fully ruled out, but the group itself looks complete).
- **Internal storage is eMMC** (`sprdboot.flash=emmc`), on **sdio3**
  (`androidboot.boot_devices=soc/soc:ap-apb/201d0000.sdio`). `sdio0` is the microSD slot. The reeder is
  UFS internally, so its storage nodes must not be copied. `CLK`/`SDHCI_SPRD` promotion in `pmos.config`
  was therefore the right call and UFS is irrelevant for this device.
- Other confirmed board values: `lcd_base=9e000000` (framebuffer region), `lcd_id=ID416002`,
  `logo_bpix=24`, `androidboot.pmic.chipid=2730` (SC2730 - so `sc2730.dtsi` is correct),
  `androidboot.slot_suffix=_a`, `androidboot.flash.locked=0`, `verifiedbootstate=orange` (unlocked).
- No `lcd_*` timing parameters are on the cmdline (base kernel params come first, then the `lcd_*` ones
  appear only as name/id/base/size/bpp) - so the panel timings must come from the board DT, i.e. the
  `&panel` fragment for the selected variant in dtbo entry 18.

# Extracted from the board device tree (dtbo entry 18, id 0x1900)
Decompiled with `tools/dtbo-extract.py` + `tools/dtb-dump.py` from the dtbo dump in the phone's
Download folder. Entry 18 is `model = "Spreadtrum UMS9230-1H10-GO Board"`, `compatible =
"sprd,ums9230-1h10-go"`.

- Panel node for this unit: `lcd_td4160_hx_mipi_hdp_x6525`, with `sprd,lcm_ic_name = "TD4160"`,
  `sprd,lcm_ic_vendor = "HX"`, `sprd,lcm_ic_inch = "6.56"`, `sprd,phy-bit-clock = 1008000` kbps.
  `display-timings/timing0` is the native mode (`native-mode = <0x02>`): 153.6 MHz, hfp 155 / hsa 4 /
  hbp 80, vfp 1020 / vsa 4 / vbp 32 -> 959x2668, i.e. 60.03 Hz.
- The board DT's supplier table pairs panel with touch:
  `supplier-1 = "lcd_td4160_hx_mipi_hdp_x6525, omnivision, td4160"` (0 = txd/omnivision,
  2 = ft8057s/focaltech) - independent confirmation of the runtime finding.
- Touch GPIOs are **irq = ap_gpio 16, reset = ap_gpio 145** (both flag 0 = active-high), SPI 8 MHz
  (`ubl-max-freq = 0x7a1200`), `spi-mode = 3`. The generic downstream `tp/` node's 144/146 belong to a
  different board.
- Keys: volume-down `ap_gpio 124` (active-low), volume-up `ap_gpio 4` (active-high), power `pmic_eic 1`.
- Charging is a Transsion `tran_charger` around an **Awinic AW32257** (`chargers = "aw32257"`).
  Mainline has no AW32257 driver and the DT carries no address; the bq2560x/bq2597x parts in the stock
  config belong to other 1h10 variants.
- There is **no PWM backlight node**: brightness is written into the panel over DCS
  (`sprd,backlight-param-write = 1`, 12-bit, `sprd,max-level = 0xfff`, default 0xa5a).
- Panel reset is `ap_gpio 50` with flag 0 (active-high) - the reeder's driver assumes active-low, so
  this is the first thing to flip if the panel stays dark.

# First boot (SSH over USB)
1. On GitHub: Actions → kernel → Run workflow. Mode `config` is the olddefconfig gate and does not need clang. Mode `image` also builds Image and modules with kernel.org LLVM 14 and `gcc-aarch64-linux-gnu`. The kernel ref defaults to `bpf-a17-selinux-test`.
   Locally: `PMOS_KERNEL_MODE=config ./build-kernel.sh <kernel tree>`, or `./build-kernel.sh <kernel tree> <clang dir>` for the full build. No `pmos` branch is required.
2. Build a **gzip** postmarketOS initramfs (kernel 5.4 cannot unpack zstd)
3. Back up boot_a, check `fastboot getvar current-slot`, then `./repack.sh Image initramfs.gz` and `fastboot flash boot_a boot-pmos.img`
4. Flash the rootfs to **`super`**, not `userdata` (sparse) — that is the partition the UMS9230 port uses (`deviceinfo_flash_fastboot_partition_rootfs="super"`). This erases Android data. The initramfs looks for the `pmOS_root` label
5. On the host a `rndis` USB network interface should appear. Add `pmos.debug-shell` to the cmdline if it does not
If the phone reboots into Android first-stage init, the bootloader ignored the boot ramdisk and the vendor ramdisk must be replaced.

# Build notes
- No `pmos` branch is needed: build-kernel.sh merges pmos.config onto the stock Helix config in an out directory. The workflow and the local script share that gate: every `=y` and every turned-off symbol in `pmos.config` must survive `olddefconfig`.
- MODULE_SIG and MODULE_SIG_ALL stay on (only MODULE_SIG_FORCE is turned off), so modules are still signed; built-in drivers need no key to boot.
- The release string is normally `5.4.302-Helix+` (the `+` disappears on an annotated-tag checkout), which is what the kernel APKBUILD expects.
- Correction to an earlier note here: `deviceinfo_header_version="4"` does **not** drop the DTB. boot-deploy builds a vendor_boot.img for v3/v4 and embeds the DTB from `deviceinfo_dtb` (the kernel package's dtbs) with mkbootimg; `deviceinfo_flash_offset_*` are ignored at v4. Flashing boot alone with `repack.sh` is a fallback, not a requirement. See README.
