# Device tree for the Infinix X6525

`ums9230-infinix-x6525.dts` is a **draft skeleton**, not a working device tree. It belongs in the
mainline tree at `arch/arm64/boot/dts/sprd/` (the `ums9230` branch of
[codeberg.org/ums9230-mainline/linux](https://codeberg.org/ums9230-mainline/linux)), next to
`ums9230-reeder-s19mps.dts` — its structural template.

## Where each value came from

| Section | Source | Status |
|---|---|---|
| `compatible`, `aliases`, `chosen` | device's own stock images (see `../NOTES.md`) | traced |
| `reserved-memory` | reeder DTS | address/size need verification |
| `backlight` | downstream `ums9230-1h10_go-overlay.dts` (pwm ch 2, 40000 ns) | traced, table TODO |
| `gpio-keys` volumedown | downstream 1h10-go (ap_gpio 124) | traced; power/volup TODO |
| storage | — | **TODO: UFS vs eMMC** |
| USB (`hsphy`, `usb`) | reeder (MUSB is the same controller) | structure traced, role-switch provider TODO |
| chargers | downstream 1h10-go + stock config (`BQ2560X`, `BQ2597X` on i2c5) | traced |
| panel | — | **TODO: no mainline driver exists** |
| touchscreen | downstream `tp/ums9230-spi3-gpio144-145-tp.dtsi` (SPI3, gpio144/146) | GPIOs traced, **vendor TODO** |
| `cpufreq`, `gpu`, `modem`, codec, uart | reeder (same SoC) | traced |

## Filling in the TODOs

1. **Panel and touch** — read them off the running stock device; the kernel config cannot tell you,
   because the stock config enables all four touch vendors and all panel variants:

   ```sh
   adb shell cat /proc/cmdline                       # lcd_name=, tp_vendor_id=
   adb shell cat /proc/modules | grep -iE 'focal|tcm|himax|chipone|fts'
   ```

2. **Storage, GPIOs, regulators** — decompile what the bootloader actually hands over. The base DTB
   matches `ums9230.dts` in the stock tree (`model = "Spreadtrum UMS9230 1H10 SoC"`), and board
   configuration comes from dtbo entry 18 (`UMS9230-1H10-GO Board`):

   ```sh
   dtc -I dtb -O dts -o base.dts   <dtb from vendor_boot>
   dtc -I dtb -O dts -o board.dts  <dtbo entry 18>
   ```

   Check `&sdio0`/`&sdio1`/`&ufs` (`status`, `non-removable`), the `gpio-keys` block, the backlight,
   the charger node's bus, and the panel/touch reset GPIOs against this file.

## Still missing before it can boot a mainline kernel

1. **Panel driver.** None of `td4160`/`ft8057s` exists in mainline. Template:
   `panel-chipone-icnl9916-720x1600.c` (from the same tree). The init sequence is in the decompiled
   dtbo from step 2.
2. **Touch driver.** Mainline has no omnivision TCM driver; `edt-ft5x06` covers some FocalTech parts
   only. The downstream driver for whichever part is fitted is the port source.
3. **U-Boot board.** The U-Boot fork only has `reeder-s19mps`. A new defconfig + DT is needed;
   the SoC-level drivers (clk, serial, SDHCI, ADI, UFS) are already there.

## Upstreaming checklist

- `Documentation/devicetree/bindings/vendor-prefixes.yaml`: add `^infinix,.*` — **not present today**.
- `Documentation/devicetree/bindings/arm/sprd/sprd.yaml`: the `ums9230` enum currently lists only
  `reeder,s19mps`; add `infinix,x6525`.
- Note that Codeberg's rules restrict LLM-generated contributions — write and sign off the patches
  you send upstream yourself.
