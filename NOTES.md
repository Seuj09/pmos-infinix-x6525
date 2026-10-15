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

## USB, audio and pstore (same live tree)

- **USB**: the MUSB node (`usb@64900000`) runs `dr-mode = "peripheral"` with
  `extcon = <&extcon-gpio &pmic_typec>` (the VBUS pin plus the PMIC Type-C
  controller), `usb-phy = <&hsphy>` and `vbus-supply = <&otg-vbus>`. Mainline's
  `musb-sprd.c` overrides `dr_mode` from the *build* config (`USB_MUSB_HOST` wins
  over `USB_MUSB_GADGET`), which is why the board DTS keeps the reeder's role
  switch: with both modes built, the port comes up as host until the role switch
  says otherwise.
- the Type-C/PD controller is `typec@380` (`sprd,sc2730-typec`,
  `sprd,sc27xx-typec`) - one node in mainline, `pd@e00` with `sprd,sc2730-pd`,
  driver `sc27xx_pd.c`. Its `vbus` regulator is **optional** there: a missing
  supply is `-ENODEV` and tolerated, the source role is all that is lost.
- the AW32257's `otg-vbus` child is a bare node (just `regulator-name`; the
  vendor charger driver registers the regulator itself) and the USB node consumes
  it as `vbus-supply`. Mainline's `bq2415x_charger.c` mentions no regulator at
  all - grep it - so there is nothing for the board DTS to point at.
- **speaker amp**: `sound@0` carries `sprd,spk-ext-pa-gpio = <&ap_gpio 113 0>`,
  the amp enable line (active-high) where the reeder's is `ap_gpio 136`. The card
  is `unisoc,vbc-v4-codec-sc2730` with 30 `sprd-audio-card,dai-link` children and
  `sprd,spk-ext-pa-info = <0 0 0xd 0>` (not interpreted).
- **pstore**: the live `ramoops@fff80000` is `reg = <0 0xfff80000 0 0x40000>` with
  console/pmsg/record sizes of `0x8000` each - exactly what the board DTS had
  marked unverified, so it is now confirmed rather than inherited.
- **framebuffer**: `logobuffer@9e000000` reserves `0xab0000` (11.2 MB) at the same
  base, i.e. the vendor keeps more slack than one 720x1612x4 frame (`0x46d000`).
  The board reserves one frame, which is all the bootloader and U-Boot draw into.

## U-Boot board, reverified against the fork
- **it builds, and the artifact is this board's**: a native `make ARCH=arm` from the fork's
  `ums9230` tip plus the two patches finishes with no errors and passes U-Boot's own `OFCHK`
  check, and the `u-boot.bin` it produces (450,536 bytes here, 452,376 in CI) embeds a
  **14,920-byte DTB** - the same size CI's does - containing `Infinix` and `201d0000` and no
  `reeder`, with the 4 GiB memory node inside. Every defconfig symbol takes effect except
  `CONFIG_SYS_RELOC_GD_ENV_ADDR`, which no longer exists in the fork's Kconfig; the reeder's
  defconfig has the same dead line, so ours mirrors it rather than diverging.


- the board DTB needs **no** `arch/arm/dts/Makefile` entry: `scripts/Makefile.dts` puts
  `$(CONFIG_DEFAULT_DEVICE_TREE).dtb` into `dtb-y` itself.
- `configs/infinix-x6525_defconfig` differs from `reeder-s19mps_defconfig` only by dropping the UFS
  stack (`CMD_UFS`, `SCSI`, `UFS`, `UFS_SPRD_UMS9230`) - verified by diffing the two files.
- `arch/arm/mach-sprd/Kconfig` selects ARM64 for `TARGET_UMS9230` (hence `ARCH=arm` on the command
  line), and its defaults (`TEXT_BASE` 0x9f000000, `SYS_LOAD_ADDR` 0x90000000) are overridden in the
  defconfig.
- **`u-boot.bin` does carry the DTB** (was an open question): the artifact CI built for `72b25da`
  (452,736 bytes) has the FDT magic at `0x6ae38`, 14,920 bytes, and that blob holds `Infinix`,
  `ums9230` and `simple-framebuffer` but not `reeder` - a fresh board tree, not a leftover. Dumped out
  of the artifact, its `/memory@80000000` is the 4 GiB window above. So installing `u-boot.bin` as the
  boot.img payload, the way `u-boot-jolla-c2` does, is correct.

# Public forks (what pmaports can fetch)

Both trees are published as forks of the GitHub mirrors of the Codeberg repos, each with an `x6525`
branch that is the upstream base plus this port's commits and nothing else:

| Tree | Fork and branch | Tip |
|---|---|---|
| kernel | `github.com/Seuj09/ums9230-mainline-linux`, branch `x6525` | `2f0f93b0cb27358ee3238eca1c8fd6a212b38a63` |
| U-Boot | `github.com/Seuj09/ums9230-mainline-u-boot`, branch `x6525` | `d169d38cab37a39282c96a1bfa0d32aff5d326df` |

The kernel branch is the tag `v7.2-rc6-ums9230-0` plus the ten patches in `patches/upstream/`, one
commit each (verified: the subjects match the patch files one for one and the tree's files are
byte-identical to `dts/`, `drivers/` and `bindings/`). The U-Boot branch is the fork's `ums9230` plus
its two board patches. Both were made by `git am`-ing the series, so `git format-patch` from either
branch regenerates the patches - the branches are the source of truth now, not the patch files.
The kernel branch is force-updated whenever the series changes (it was, to pick up the renamed
thermal zones and the ninth patch): patch 9 lets the sprd GPIO binding accept hog nodes, which
`charger-en-hog` in our DTS needs - the binding is `additionalProperties: false` without the
`patternProperties` block that other GPIO bindings carry, so the board failed `dtbs_check` on a
binding it could not satisfy. That fix is independent of this board and can go upstream on its own.
`pmaports/device/testing/u-boot-infinix-x6525/APKBUILD` already builds from the U-Boot branch's tip
(sha512 in place); the kernel side needs nothing until either a staging package is wanted or the
series lands upstream.

**Where patches go, and where they do not.** `ums9230-mainline/linux` releases by *tag*
(`v6.12` … `v7.2-rc6-ums9230-0`, one per kernel version); its two branches (`ums9230`,
`ums9230-opencp`) are older, divergent lines whose trees differ from the newest tag by ~17,300 files.
So our patches are cut against the newest *tag* - correct for pmaports, which pins the same tag - and
a Codeberg PR against `ums9230` would be aimed at a stale tree: the kernel series should go to the
maintainer by mail or issue. U-Boot is the opposite, with one `ums9230` branch that our two patches
`git am` cleanly onto, so a PR from the fork branch is the right mechanism there.

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

**Gathering what is still unknown:** `sh tools/collect-live.sh` (root shell on the phone, stock system)
writes one text file with the `board-thmzone` and thermistor tables, the state of `ap_gpio 115`
(`charge,chg-pd-gpio`), regulator names and voltages, every I2C/SPI device and its driver, the
WiFi/Bluetooth/audio/camera hardware, every power-supply attribute and the relevant `dmesg` lines.
A first run (`x6525-live.txt`) settled the GPIO numbering (ap_gpio N = debugfs number minus 64 for
gpiochip4; eic_sync base 320, eic_async 368, pmic_eic 48), the panel/touch/key lines and the charger
enable. It still lacks the thermistor tables and the compatible list (the script followed a symlink
badly; fixed since), so run it once more. The stock system shows a Unisoc `sprd_wlan_combo`/`wcn_bsp`
WiFi/BT stack (no known mainline driver), an `sprdphone-sc2730` audio card with several amplifiers,
and a sensorhub. The thermal zone, the charge-pd GPIO, the WiFi/BT firmware package and the sensors
below all need that data and cannot be written from the vendor tree alone (the vendor's generic
1h10 overlay has a `board-thmzone`, but this board's own values are only on the device).

U-Boot board, smallest first:
1. ~~**Fix the memory node** in `uboot/dts/ums9230-infinix-x6525.dts` to
   `reg = <0x0 0x80000000 0x0 0xfffff000>` (4 GiB - see Memory above). This is the one change that
   decides whether the board boots at all.~~ Done.
2. ~~Finish the battery node: add `ocv-capacity-table-0`, `resistance-temp-table` and
   `voltage-max-design-microvolt` from the tables above, the way the reeder's board DTS does - the
   fuel gauge needs the OCV table for its capacity estimate and the charging animation. Done (OCV, resistance-temp and fast-charge threshold; `voltage-max-design-microvolt` not added - not read off the device).~~
3. ~~Confirm the DTB is inside the artifact the pmaports package installs.~~ Done - the CI artifact
   carries it, see "U-Boot board, reverified against the fork" above.
4. ~~Then upstream the two `patches/upstream-uboot/` patches and drop the `WIP:` prefixes.~~ The
   prefixes are gone - both patches were regenerated with `git format-patch` so the diffstat, blob
   hashes and subjects are derived rather than hand-kept, and checked with `git am` in order. All
   that is left is sending them to the fork.

Kernel series: the `WIP:` prefixes are gone from patches 3 and 4 too, and with them the `DRAFT`
lines in the three driver headers. What made them WIP has been dealt with - the DTS has no TODOs left
and its header no longer calls itself a skeleton, so the only caveat left is the honest one: nothing
has run on hardware yet, and `FIRST_BOOT.md` carries what that means for each part. Patches 3, 4, 6
and 8 were regenerated with `git format-patch` (every stat, bar and hash derived) and `git am`-verified
byte for byte, since the driver comment change touches 6 and 8 as well. Same rule as the U-Boot pair:
sending them is the remaining step.

Charger (resolved - no new driver):
1. Register map confirmed against `drivers/power/supply/bq2415x_charger.c`: register 0x03 = 0x53 gives
   vender 2, part number 2, revision 3; at I2C address 0x6a the driver's `bq2415x_detect_chip()` maps
   part number 2 to BQ24158 and revision 3 to "1.0" - the exact string the stock driver prints. The
   binding (`power/supply/bq2415x.yaml`) already lists `ti,bq24158`, and its property names
   (`ti,current-limit`, `ti,weak-battery-voltage`, `ti,battery-regulation-voltage`, `ti,charge-current`,
   `ti,termination-current`, `ti,resistor-sense`) are the ones the vendor node uses.
2. Units differ: mainline wants mA / mV / mohm, the vendor node has uA for three of them
   (650000 -> 650, 100000 -> 100, 60000 -> 60). The DTS now has `charger@6a` on `&i2c3` and
   `&sc2730_fgu { power-supplies = <&charger>; }`; the dtb builds.
3. USB detection (drafted, untested): the bq2415x only auto-selects its mode from a power supply that
   reports `CURRENT_MAX`, and mainline has none for this SoC (`sc2731_charger` needs a usb_phy with
   charger detection). `drivers/extcon-charger-detect.c` (patches 7/8, glue 0003) turns the extcon
   VBUS pin the stock tree reads (`pmic_eic 0`, via `linux,extcon-usb-gpio`) into that supply,
   `ti,usb-charger-detection` points at it. A VBUS pin cannot tell a wall charger from a PC, so input
   is limited to 500 mA until BC1.2 detection in the SC2730 has a driver (the stock system does it with
   its `sprd_bc1p2` module, a possible model for a mainline port). `charge,chg-pd-gpio` (ap_gpio 115)
   is named `charger_en` on the stock system and sits low while charging, so the DTS hogs it
   output-low. Thermistors are now described (see below). Still open: the `board-thmzone` thermal zone; and whether mainline's `sc27xx_fuel_gauge.c` understands the
   vendor's JEITA tables. The bq2415x driver has no OTG regulator, so the Type-C source path has no
   VBUS regulator yet. `tran_charger` and `charger-manager` are not carried over.

The ROM, and the first boot:
- **the kernel package is drafted** in `pmaports/device/testing/linux-postmarketos-unisoc-ums9230/`:
  pmaports' own package with the ten patches added to `source=` (verified to apply with `patch -p1`,
  which is what `default_prepare` uses, reproducing `dts/`, `drivers/` and `bindings/` byte for byte)
  and the five symbols its config was missing. That config is pmaports' own and is what the ROM's
  kernel actually uses, so CI now checks those five survive `olddefconfig` in it, last in the job
  because the check replaces `.config`.
- **the firmware needs nothing pressed**: this repository was made public on 2026-10-14 for exactly
  this reason, so `firmware-infinix-x6525`'s `source=` is the tarball in `firmware/` served straight
  from it, pinned to the commit that added it (`186e3e0f`), and the build workflow fetches that URL
  and checks it against the package's sha512 on every push. Verified by hand as well: 124,616 bytes,
  the hash in the APKBUILD. (Use `raw.githubusercontent.com/<owner>/<repo>/<commit>/<path>` for this
  sort of thing - `github.com/<owner>/<repo>/raw/<branch>/<path>` answers with an HTML page, which
  would have been a package that downloads a web page.) `.github/workflows/firmware-release.yml` can
  still put a versioned copy on this repository's releases, on a button press, with no token beyond
  the workflow's own; nothing depends on it. The earlier advice to copy the device package without
  the firmware package is obsolete. The image is `proprietary`, which is why the device package only
  recommends it: without it a ROM boots and has no touchscreen.
- **then it is the phone**: `pmbootstrap` build and flash per `FIRST_BOOT.md`, and the hardware list
  there - panel reset polarity, the DCS brightness curve, the eMMC/SD phy timing, and the touch
  firmware download, which is the likeliest first failure. `.github/workflows/rom.yml` (Actions →
  *rom* → Run workflow) does the same build on GitHub's arm64 runner and uploads the artifacts, so
  the build needs neither this container nor any local install; arm64 because on x86_64 the kernel
  build goes through qemu-user and takes hours.
- **what building it in CI taught, none of which anything local had run**: `pmbootstrap init` cannot
  run unattended, so the workflow writes the config file init would have written *and* the `version`
  marker init creates in the work directory (`pmb.config.work_version` - without it pmbootstrap
  refuses the directory as needing migration); `abuild` refuses an APKBUILD with no `url=`, which is
  how the first run died, on the first of our packages it reached; `pmbootstrap export` fills its
  folder with **symlinks** into the work directory, so the upload copies it out with `cp -rL` first;
  and the source check that had been "verifying" the firmware URL never expanded `$_tarball` - it fed
  curl a URL that was not one and read the 404 as "not published yet", so it passed for a file that
  was published and hashing correctly all along. It now sources the APKBUILD and lets the shell
  expand it. And `boot-deploy` will not build a boot image without `mkbootimg`, which is in
  `android-tools`: `deviceinfo_generate_bootimg="true"` therefore obliges the device package to
  *depend* on it, or `mkinitfs` fails the whole install. That is where the fourth run stopped - with
  the kernel compiled from the ten patches, U-Boot built, and both packages built.
- **the ROM built, 2026-10-15** (run 38668586983, 48 minutes): `x6525-rom` holds the five things
  `export` produces - `boot.img` (U-Boot as the payload, which is the chainload design),
  `infinix-x6525.img`, `initramfs`, `vmlinuz` and `dtbs/ums9230-infinix-x6525.dtb`. Nothing has been
  flashed: the next step is `FIRST_BOOT.md`, on the phone, with the backups it lists first.
- **what that image is, measured from the artifact** (`gh run download 38668586983 -n x6525-rom`)
  rather than from the sources: `infinix-x6525.img` is a complete MBR+GPT disk, 2,664,448 sectors.
  Partition 1 (Linux extended boot, LBA 2048, 510,656,512 bytes, label `pmOS_boot`) holds
  `/extlinux/extlinux.conf`, `/vmlinuz`, `/initramfs`, the DTB and a copy of `boot.img`; partition 2
  (Linux root, LBA 999424, 851,443,712 bytes, label `pmOS_root`) is the root filesystem. The extlinux
  append line is `quiet splash plymouth.ignore-serial-consoles plymouth.prefer-fbcon
  pmos_boot_uuid=65fc212d-2829-4823-924c-e9da2fbd98d0 pmos_root_uuid=
  bd9271aa-7108-4b4b-9f60-0885c8569403 pmos_rootfsopts=defaults`, and those UUIDs are the two
  filesystems' own, so the initramfs finds them by `blkid --uuid` wherever the image was written.
  `boot.img` is header v4, 458,752 bytes: payload = this board's `u-boot.bin` (448,632 bytes, FDT at
  0x69e30 with `Infinix` and the 4 GiB memory node) plus a 4 KiB dummy ramdisk.
- **why it cannot be flashed with `flasher flash_rootfs`**: that writes the whole 1.36 GB disk image
  into `super`, and U-Boot cannot see a partition table nested inside a partition -
  `drivers/block/blk-uclass.c`'s `part_create_block_devices()` returns early unless the device is
  `UCLASS_BLK`, while a partition is `UCLASS_PARTITION` - so `bootcmd=bootflow scan -lb mmc`
  (`board/unisoc/ums9230/ums9230.env`) finds no bootflow and the phone sits at the U-Boot prompt. The
  image goes onto a microSD card whole instead; `FIRST_BOOT.md` has the steps. The card may be larger
  than the image - the kernel tolerates a smaller disk's protective MBR on a larger one on purpose
  ("to support dd'ing an image from a smaller disk to a larger disk", `block/partitions/efi.c`).
- **the pre-flash audit's corrections (2026-10-15)**, all read off the running system's own tree,
  which is the authority the DTS header names: the touch interrupt parent is `eic_async` 16, not the
  board overlay's `ap_gpio` 16 (on the AP GPIO the controller never sees the first IDENTIFY);
  volume-up is `pmic_eic` 4, not `ap_gpio` 4; the eMMC's `vqmmc-supply = <&vddsdio>` is gone
  (`vddsdio` is the microSD slot's IO rail); and `&wcn` now carries the three supplies and two GPIOs
  its driver in this tree requires and the dtsi does not default to. Two diagnostics came with them:
  `CONFIG_SERIAL_SPRD=y` in the kernel package's config (the UART in `stdout-path` was inert without
  it) and `kernel-cmdline.conf` with `loglevel=7` in the device package (the distro cmdline ships
  `quiet`).
- **which copy of U-Boot the ROM ships**: the u-boot package builds from the *fork's* tarball at
  `_commit` (branch `x6525`), while `uboot/` here is what CI builds; the two are byte-identical today
  (checked against the fork), so a change to `uboot/` needs a push to the fork and a `_commit`/sha512
  bump before the ROM can carry it. The kernel is the other way round: its package builds from the
  codeberg tag plus `patches/upstream/`, so `dts/` reaches the ROM through patch 0003 - which is why
  CI checks that one against the other.
- **what the built U-Boot can actually do** (from its own `.config`, built locally with the board
  overlay): `FS_EXT4`/`CMD_EXT4`/`BOOTMETH_EXTLINUX`/`BOOTSTD_FULL` are all `=y`, so the extlinux
  bootflow on an ext4 card partition is exactly the path it was configured for, and `SPRD_SERIAL`,
  `VIDEO`+`VIDEO_SIMPLE` give it both consoles. `ENV_IS_NOWHERE=y` means the `bootcmd` in
  `board/unisoc/ums9230/ums9230.env` (`bootflow scan -lb mmc`) is compiled in and always used. It has
  no regulator driver for the PMIC and `sdhci-sprd.c` touches no rails, so the card slot is powered
  by whatever the stock bootloader left on - the same situation as the reeder's board, whose U-Boot
  DTS enables `&sdio0` exactly the way this one does. `CONFIG_FASTBOOT_FLASH` is **off**: it
  enumerates as a fastboot device but cannot write a partition.
- **which runner does what, and why**: `rom.yml` runs on GitHub's arm64 runner because building the
  image means attaching it to a loop device, and the Namespace profile's runner is a container whose
  device cgroup refuses the block device - the nodes can be made and `losetup -f` answers, but
  attaching fails with `Operation not permitted`. `build.yml` and `firmware-release.yml` run on
  `namespace-profile-1`, where both are green and the kernel compiles in 10 minutes against 43 on
  GitHub's runner. If Namespace offers a VM-based profile, moving `rom.yml` there is one line and
  would roughly quarter the build.
- `firmware-infinix-x6525-wcn` (WiFi/Bluetooth) does not exist yet; touch under unl0kr needs the
  touch module and the HDL image in a `modules-initfs` file; the wiki device page is required at MR
  time; and the SD card-detect is settled (`eic_sync` 35, ACTIVE_LOW, empty slot reads high).

# First boot (SSH over USB)

*This section and "Build notes" below are the **downstream 5.4** path, kept as the record of it. The
`kernel` workflow that used to run the build on GitHub has been removed; the mainline first boot is
[FIRST_BOOT.md](FIRST_BOOT.md).*

1. Locally: `PMOS_KERNEL_MODE=config ./build-kernel.sh <kernel tree>` for the olddefconfig gate (it needs no clang), or `./build-kernel.sh <kernel tree> <clang dir>` for the full build with kernel.org LLVM 14 and `gcc-aarch64-linux-gnu`. No `pmos` branch is required. The kernel ref the removed workflow used was `bpf-a17-selinux-test`.
2. Build a **gzip** postmarketOS initramfs (kernel 5.4 cannot unpack zstd)
3. Back up boot_a, check `fastboot getvar current-slot`, then `./repack.sh Image initramfs.gz` and `fastboot flash boot_a boot-pmos.img`
4. Flash the rootfs to **`super`**, not `userdata` (sparse) — that is the partition the UMS9230 port uses (`deviceinfo_flash_fastboot_partition_rootfs="super"`). This erases Android data. The initramfs looks for the `pmOS_root` label
5. On the host a `rndis` USB network interface should appear. Add `pmos.debug-shell` to the cmdline if it does not
If the phone reboots into Android first-stage init, the bootloader ignored the boot ramdisk and the vendor ramdisk must be replaced.

# Build notes
- No `pmos` branch is needed: build-kernel.sh merges pmos.config onto the stock Helix config in an out directory. Its gate, which the removed workflow ran too: every `=y` and every turned-off symbol in `pmos.config` must survive `olddefconfig`.
- MODULE_SIG and MODULE_SIG_ALL stay on (only MODULE_SIG_FORCE is turned off), so modules are still signed; built-in drivers need no key to boot.
- The release string is normally `5.4.302-Helix+` (the `+` disappears on an annotated-tag checkout), which is what the kernel APKBUILD expects.
- Correction to an earlier note here: `deviceinfo_header_version="4"` does **not** drop the DTB. boot-deploy builds a vendor_boot.img for v3/v4 and embeds the DTB from `deviceinfo_dtb` (the kernel package's dtbs) with mkbootimg; `deviceinfo_flash_offset_*` are ignored at v4. Flashing boot alone with `repack.sh` is a fallback, not a requirement. See README.

# Thermistors (second live dump)

board (`tboard`), pa and chg are `generic-adc-thermal` on SC2730 ADC channels 1, 2 and 4, all with
one NTC table (-40 C at 1131 mV down to 125 C at 43 mV). The stock zones have no trips and no
polling, so the DTS only exposes the temperatures. The zones are named `board-thermal`, `pa-thermal` and `chg-thermal` (stock: `*-thmzone`);
the thermal-zones schema only accepts `<name>-thermal`. chg reads about 4 C (probably unpopulated).
The SD card-detect line `eic_sync` 35 read high with the slot empty (confirmed), so the DTS uses GPIO_ACTIVE_LOW.
