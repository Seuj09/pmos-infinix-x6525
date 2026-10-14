# Drivers for the X6525 port

`panel-td4160-hx.c` goes in the mainline tree at `drivers/gpu/drm/panel/` (the `ums9230` branch of
[codeberg.org/ums9230-mainline/linux](https://codeberg.org/ums9230-mainline/linux)), next to
`panel-chipone-icnl9916-720x1600.c`, whose structure it follows.

Everything panel-specific in it now comes from **this device's own board device tree** (dtbo entry 18),
not from a sibling panel:

- the DCS init sequence (355 packets, extracted and converted, with the vendor's `0x13` delay opcodes
  turned into `mipi_dsi_msleep`);
- the reset sequences (`sprd,reset-on-sequence = <1 5>, <0 5>, <1 20>`);
- the mode timings, from `display-timings/timing0` - the native mode - which are self-consistent at
  60.03 Hz;
- the DCS backlight (12-bit, `sprd,max-level = 0xfff`; the board has no PWM backlight).

The sequence can be regenerated at any time:

```sh
python3 -I tools/dtbo-extract.py dtbo.img -n 18 -x board.dtb
python3 -I tools/dtb-dump.py board.dtb -p sprd,initial-command -r \
    | python3 -I tools/lcd-dtsi-to-c.py --stream
```

Still open, in order of what would bite first:

1. the panel reset polarity (vendor DT says active-high; the reeder driver assumes active-low);
2. the brightness curve - the vendor's `brightness-levels` table is not reproduced, so brightness is
   linear;
3. the charging driver (Awinic AW32257 via Transsion `tran_charger`) - unrelated to the panel, but it
   has to be ported separately before the battery charges under mainline;
4. the touch driver - see below.

## `ovt-tcm-spi.c` - touchscreen (new, untested on hardware)

Goes in `drivers/input/touchscreen/`; `../patches/upstream/0005-*.patch` (binding) and `0006-*.patch`
(driver, with the Kconfig `TOUCHSCREEN_OVT_TCM_SPI` and Makefile entries) are the submission copies,
and `../patches/0002-x6525-touch-glue.patch` carries the two build hunks that CI applies. It compiles
- CI builds the object; the binding is `../bindings/omnivision,tcm-spi.yaml`.

It is written from how the stock `omnivision_tcm` driver behaves on the wire, not copied from it. The
chip has no flash, so after every reset the driver downloads firmware from a `hdl_firmware_*.img`:
ROM-boot IDENTIFY, `CMD_ROMBOOT_DOWNLOAD`, run bootloader, then `APP_CONFIG` / `DISPLAY` / `OPENSHORT`
on request, then it reads app info, fixes the touch report layout and registers a multitouch input
device. A panel reset resets the touch IC as well; the driver sees the new ROM-boot IDENTIFY and
downloads again on its own.

Open points, in order of what would bite first:

1. **Which image - answered.** The stock *tree's* driver does not select by panel name at all: its
   `strstr()` table only knows the "cw" variants and bails out when none of them match. The module the
   device actually runs asks for `hdl_firmware_01.img` - the only `hdl_firmware` name in its strings,
   and `/vendor/firmware` holds `hdl_firmware_00.img` and `_01.img`. So `firmware-name` is
   `postmarketos/sprd/hdl_firmware_01.img` (note the double digit - the tree's single-digit names
   would not resolve), and `../pmaports/device/testing/firmware-infinix-x6525/` packages it. The file
   still has to be copied off the device and republished somewhere fetchable.
2. The first hardware run will show whether the 9-byte first read plus continued reads match the
   chip's framing, and whether 8 MHz in SPI mode 3 is right with the SoC's SPI controller (the
   ROM-boot download is a single large transfer, as in the stock driver).
3. Not implemented: the older F35/RMI download path, flash update, diagnostics, gestures and
   double-tap wake, the stock sysfs and watchdog. Suspend only sends deep sleep / exit deep sleep.
4. The IRQ is now level-low in the DTS (the stock driver also reads only while the line is low); the
   previous edge-falling setting could miss the first IDENTIFY report.

## `extcon-charger-detect.c` - USB charger detection (new, untested on hardware)

The bq2415x charger chooses its input mode from a power supply that reports `CURRENT_MAX`
(`ti,usb-charger-detection`). Nothing in mainline provides one for this SoC, so this small driver turns
an extcon (here `linux,extcon-usb-gpio` on the VBUS pin, `pmic_eic 0`) into that supply: DCP/CDP/SDP
map to configurable limits, and a plain VBUS pin - which cannot tell a wall charger from a PC - gets
500 mA. It is conservative on purpose. Patches 7 and 8 in `../patches/upstream/`, glue in
`../patches/0003-x6525-charger-glue.patch`, binding `../bindings/linux,extcon-charger-detect.yaml`. It
compiles clean with clang and `W=1`.

Open: the VBUS pin's polarity and whether `extcon-usb-gpio` (written for USB role detection) is happy
with only a VBUS line on this PMIC GPIO; the 500 mA ceiling until real BC1.2 detection exists.
