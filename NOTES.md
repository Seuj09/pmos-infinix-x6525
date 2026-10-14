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
  Mainline has no AW32257 driver and the dtbo fragment carries no address; the bq2560x/bq2597x parts in
  the stock config belong to other 1h10 variants. **The address, the node and what the chip actually is
  are all in the live device tree now - see "The running device's own device tree" below.**
- There is **no PWM backlight node**: brightness is written into the panel over DCS
  (`sprd,backlight-param-write = 1`, 12-bit, `sprd,max-level = 0xfff`, default 0xa5a).
- Panel reset is `ap_gpio 50` with flag 0 (active-high) - the reeder's driver assumes active-low, so
  this is the first thing to flip if the panel stays dark.

# The running device's own device tree

The stock kernel exposes its expanded tree, so these values are read off the phone instead of being
inferred from a dtbo: `/proc/device-tree` (same thing as `/sys/firmware/devicetree/base`).
`tools/dtdir-dump.py <node>` prints one node, `-R` walks a subtree; a phandle resolves by looking for
the `phandle` property with the same value. This is the first place to look for board values now - it
is what the kernel was actually handed, including nodes and properties the dtbo dump does not carry.

## Charging

- `aw32257` is an **I2C** device at **3-006a**, i.e. `/soc/ap-apb/i2c@0x20100000/aw32257@6a` - bus
  `i2c3` (`20100000`), address **0x6a**, driver `aw32257-charger`, `compatible = "awinic,aw32257"`.
- its node: `reg = <0x6a>`, `extcon = <&extcon-gpio>`, `monitored-battery = <&battery>`,
  `phys = <&hsphy@64570000>`, `charge,chg-pd-gpio = <&ap_gpio 115 GPIO_ACTIVE_HIGH>`, an `otg-vbus`
  regulator child, and TI-style scalars in mixed units: `ti,battery-regulation-voltage = <4400>` (mV),
  `ti,charge-current = <650000>` (uA), `ti,current-limit = <100000>` (uA),
  `ti,termination-current = <60000>` (uA), `ti,weak-battery-voltage = <3400>` (mV),
  `ti,resistor-sense = <56>`.
- **the chip identifies itself as a TI part**: `model_name` is `"chip bq24158, revision 1.0, vender code
  010"`, and its `registers` attribute dumps exactly five registers, 0x00-0x04
  (`0x00=d0 0x01=30 0x02=b6 0x03=53 0x04=59`). A five-register 0x00..0x04 map together with those
  names (`battery_regulation_voltage`, `weak_battery_voltage`, `resistor_sense`, `current_limit`) is the
  bq2415x family layout, so the AW32257 looks like a register-compatible **bq24158**. Still to confirm
  against the actual driver: the pinned tree has exactly one bq2415x driver,
  `drivers/power/supply/bq2415x_charger.c` (`CONFIG_CHARGER_BQ2415X`).
- `tran_charger` is Transsion's platform-level framework: `chargers = "aw32257"`,
  `pd_max_power = <5000000>`, `tran-thermal-zone = "board-thmzone"`, and a fast-charge current versus
  board temperature table `fchg-boardtemp-cur` = (41 C, 1.4 A) (43 C, 1.2 A) (44 C, 0.8 A).
- `charger-manager` is a **mainline** driver (`drivers/power/supply/charger-manager.c`, and
  `CONFIG_CHARGER_MANAGER` is in the pinned tree). The node: `cm-chargers = "tran_charger"`,
  `cm-fuel-gauge = "sc27xx-fgu"`, `cm-name = "battery"`, `cm-thermal-zone = "board-thmzone"`,
  `extcon = <&pmic_typec &pmic_pd>`, `monitored-battery = <&battery>`, `cm-poll-interval = <15000>`,
  `cm-charging-max = <43200000>`, `cm-discharging-max = <2700000>`, `cm-shutdown-voltage = <3100000>`,
  `cm-charge-voltage-max = <6200000>`, `cm-fullbatt-capacity = <100>`,
  `sprd,customized-fchg-psy = "tran_charger"`. It is what publishes the ac/battery/usb/wireless
  supplies.
- `sc27xx-fgu` is the fuel gauge (mainline driver), `extcon-gpio` is `linux,extcon-usb-gpio` with
  `vbus-gpio = <&pmic_eic 0 GPIO_ACTIVE_HIGH>`, and `sc27xx_typec` / `sc27xx_pd` / `sprd_tcpm` carry
  the PD path.
- loaded modules: `tran_charger aw32257_charger sc27xx_fuel_gauge sprd_charger_manager
  sprd_battery_info sc27xx_pd sc27xx_typec sprd_tcpm extcon_usb_gpio`.

## Battery (`/battery`, `compatible = "simple-battery"`)

- 4950000 uAh design, 200000 uA charge term, 4400000 uV max, 3450000 uV min design, 140000 uOhm
  factory resistance, fast-charge threshold 4100000 uV.
- `ocv-capacity-table-0` (uV, %):
  `(4380000 100) (4312000 95) (4248000 90) (4191000 85) (4135000 80) (4081000 75) (4029000 70)
  (3977000 65) (3937000 60) (3875000 55) (3839000 50) (3813000 45) (3795000 40) (3780000 35)
  (3772000 30) (3762000 25) (3746000 20) (3722000 15) (3683000 10) (3623000 5) (3400000 0)`
- `resistance-temp-table` (C, mOhm): `(50 80) (25 100) (10 168) (0 421) (-10 688)`;
  `capacity-temp-table` (C, %): `(50 100) (25 100) (10 96) (0 60) (-10 50)`.
- it also carries `voltage-temp-table`, `first-calib-*`, `fullbatt-*` and six `*-jeita-temp-table`
  properties (sdp/cdp/dcp/pd/unknown/fchg-pd). Those are downstream extras, not `simple-battery`.

## Memory

`/memory@80000000` is `reg = <0x0 0x80000000 0x0 0xfffff000>` - a **4 GiB** window from `0x80000000` to
`0x17ff00000`, matching `androidboot.ddrsize=4096M` (`androidboot.ddrsize.range=[4096,5120)`).

This is where the U-Boot board is wrong: it copied the reeder's `0x1 0xfffff000` (8 GiB). U-Boot sizes
its RAM from that node, and `board/unisoc/ums9230/board.c` only fixes up WiFi/Bluetooth MAC addresses -
nothing corrects memory at runtime - so relocation and the stack would land above the end of DRAM.

## U-Boot board, reverified against the fork

- the board DTB needs **no** `arch/arm/dts/Makefile` entry: `scripts/Makefile.dts` puts
  `$(CONFIG_DEFAULT_DEVICE_TREE).dtb` into `dtb-y` itself.
- `configs/infinix-x6525_defconfig` differs from `reeder-s19mps_defconfig` only by dropping the UFS
  stack (`CMD_UFS`, `SCSI`, `UFS`, `UFS_SPRD_UMS9230`) - verified by diffing the two files.
- `arch/arm/mach-sprd/Kconfig` selects ARM64 for `TARGET_UMS9230` (hence `ARCH=arm` on the command
  line), and its defaults (`TEXT_BASE` 0x9f000000, `SYS_LOAD_ADDR` 0x90000000) are overridden in the
  defconfig.
- open: whether the packaged `u-boot.bin` actually carries the DTB. The pmaports package installs
  `u-boot.bin` as the boot.img payload, so it has to be self-contained - check by building and looking
  for the FDT magic in the artifact (or the size jump between `u-boot.bin` and `u-boot-dtb.bin`).

# Working from the phone shell

- this shell runs **on the phone** (Debian trixie in a container, the stock 5.4 kernel underneath), so
  `/proc/device-tree`, `/sys/class/power_supply/*` and `/proc/config.gz` are live data rather than dumps.
- `/vendor` is not mounted here, so the stock kernel modules cannot be read or disassembled from here.
- the Codeberg **u-boot** archive downloads fine (~44 MB); the **kernel** archive does not - it
  truncated every time (200 MB in, gzip "unexpected end of file"). Fetch kernel files one at a time
  instead: `https://codeberg.org/ums9230-mainline/linux/raw/tag/<tag>/<path>`. `gh`/`api.github.com`
  was unreachable from here too.
- `/proc/config.gz` (the running config) does **not** match `linux-infinix-x6525/config-helix-stock.aarch64`:
  the live one says `CONFIG_CHARGER_AW32257 is not set` and `CONFIG_CHARGER_MANAGER is not set`, yet
  `aw32257_charger` and `sprd_charger_manager` are both loaded - so those modules were built from a tree
  that is not the one that config file came from. (Downstream path only; the mainline port ignores both.)

# Next steps

U-Boot board, smallest first:
1. **Fix the memory node** in `uboot/dts/ums9230-infinix-x6525.dts` to
   `reg = <0x0 0x80000000 0x0 0xfffff000>` (4 GiB - see Memory above). This is the one change that
   decides whether the board boots at all.
2. Finish the battery node: add `ocv-capacity-table-0`, `resistance-temp-table` and
   `voltage-max-design-microvolt` from the tables above, the way the reeder's board DTS does - the
   fuel gauge needs the OCV table for its capacity estimate and the charging animation.
3. Confirm the DTB is inside the artifact the pmaports package installs (see the open item above).
4. Then upstream the two `patches/upstream-uboot/` patches and drop the `WIP:` prefixes.

Charger:
1. Confirm the register map against `drivers/power/supply/bq2415x_charger.c` (register names, bitfields
   and the vendor/revision decoding that produced "bq24158"). Everything else below depends on it.
2. Decide the driver: either add a DT front-end to `bq2415x_charger.c` (it is platform-data only today,
   and the chip really is that family's register layout), or ship a separate `aw32257` driver in
   `drivers/` next to the panel and touch ones. The separate driver is the safer of the two for
   upstream - it does not rewrite an existing driver - and gives a clean binding for the Awinic extras
   (`otg-vbus` regulator, `charge,chg-pd-gpio`, stat pin, high-impedance mode).
3. DTS glue, all values already read off the device: `&i2c3 { charger@6a { ... } }`, the `bat: battery`
   node with the real profile, `&sc2730_fgu { monitored-battery = <&bat>; power-supplies = <&charger>; }`,
   `extcon-gpio` with `vbus-gpio = <&pmic_eic 0 GPIO_ACTIVE_HIGH>`, and - if we want the vendor's charge
   policy - `charger-manager` with `cm-fuel-gauge`/`cm-chargers`.
4. Still unknown, needs a look: what provides the `board-thmzone` thermal zone that both `tran_charger`
   and `charger-manager` point at (mainline would need the sprd tsensor/ADC path), what
   `charge,chg-pd-gpio` (ap_gpio 115) actually gates, and whether mainline's
   `sc27xx_fuel_gauge.c` understands the vendor's `*-jeita-temp-table` properties at all.

Missing from before, still open:
- publish the touch firmware tarball somewhere fetchable and put the URL in the
  `firmware-infinix-x6525` APKBUILD `source=` (the tarball and its sha512 are already final).
- `firmware-infinix-x6525-wcn` (WiFi/BT) does not exist yet.
- touch under unl0kr needs the touch module and the HDL image in `modules-initfs`.
- the wiki device page, which pmaports CI checks at MR time.
- physical first boot, watching the list in "First boot" plus the panel reset polarity, the DCS
  brightness curve, eMMC on sdio3 in U-Boot and the SD card-detect line (`eic_sync` vs `eic_async`).

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
