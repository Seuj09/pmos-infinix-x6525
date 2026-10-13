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
4. the touch driver (Omnivision TCM over SPI) - not started, see `../dts/README.md`.
