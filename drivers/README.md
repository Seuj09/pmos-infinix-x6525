# Drivers for the X6525 port

`panel-td4160-hx.c` goes in the mainline tree at `drivers/gpu/drm/panel/` (the `ums9230` branch of
[codeberg.org/ums9230-mainline/linux](https://codeberg.org/ums9230-mainline/linux)), next to
`panel-chipone-icnl9916-720x1600.c`, whose structure it follows.

**Read the header comment before using it.** Two things in it are knowingly not from this device:

- the DCS sequence is generated from the 720x1280 `lcd_td4160_cw_mipi_hd.dtsi` sibling — regenerate it
  from this device's board DT with `tools/lcd-dtsi-to-c.py`;
- the mode timings are placeholders. The vendor DT has no H/V blanking, so the bootloader passes the
  real values as `lcd_*` cmdline parameters (`cat /proc/cmdline` on the stock device).

Not yet started: the touch driver (Omnivision TCM over SPI). Port source is
`drivers/input/touchscreen/omnivision_tcm/` in the stock 5.4 tree — see `../dts/README.md`.
