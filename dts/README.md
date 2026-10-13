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
| panel | device cmdline: `lcd_td4160_hx_mipi_hdp_x6525` | confirmed TD4160 HX, 720x1612; no mainline driver |
| touchscreen | device: bound driver `omnivision_tcm_spi` on `spi3.0` | confirmed Omnivision TCM; no mainline driver |
| `cpufreq`, `gpu`, `modem`, codec, uart | reeder (same SoC) | traced |

## Filling in the TODOs

1. **Panel and touch** — *done*. Read off the running stock device (the kernel config cannot tell you:
   it enables all four touch vendors as modules, and the vendor loads four of them at once). The
   decisive checks were the bound driver, not the loaded modules:

   ```sh
   cat /proc/cmdline | tr ' ' '\n' | grep -E 'lcd_name|tp_vendor_id'
   cat /proc/bus/input/devices | grep -E 'Name=|Handlers='
   for d in /sys/bus/spi/devices/*; do echo "$(basename $d) -> $(basename $(readlink -f $d/driver))"; done
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

1. **Panel driver.** Drafted in this repo: `drivers/panel-td4160-hx.c`, now carrying this device's own
   DCS sequence, reset sequence and mode timings, all extracted from dtbo entry 18 with the tools in
   `tools/`. Untested; the remaining unknowns are the panel reset polarity and the brightness curve.
2. **Touch driver.** Confirmed Omnivision TCM over SPI. No mainline driver exists, and `edt-ft5x06` is
   I2C-only so it cannot be reused. Port source: `drivers/input/touchscreen/omnivision_tcm/` in the
   stock 5.4 tree — ~390 KB of C across 20+ files plus four ~150 KB firmware images. The largest
   remaining item, and the one whose approach (full vendor port vs. minimal driver) needs deciding.
3. **U-Boot board.** The U-Boot fork only has `reeder-s19mps`. A new defconfig + DT is needed;
   the SoC-level drivers (clk, serial, SDHCI, ADI, UFS) are already there.

## Upstreaming checklist

- `Documentation/devicetree/bindings/vendor-prefixes.yaml`: add `^infinix,.*` — **not present today**.
- `Documentation/devicetree/bindings/arm/sprd/sprd.yaml`: the `ums9230` enum currently lists only
  `reeder,s19mps`; add `infinix,x6525`.
- Note that Codeberg's rules restrict LLM-generated contributions — write and sign off the patches
  you send upstream yourself.
