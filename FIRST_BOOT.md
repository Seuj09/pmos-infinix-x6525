# First boot of the mainline port

This is the checklist for the **mainline route** (U-Boot chainloaded from `boot_a`, then the
`linux-postmarketos-unisoc-ums9230` kernel with `dts/ums9230-infinix-x6525.dts`). The 5.4 route has its
own steps at the end of `NOTES.md`. Nothing below has been run on the phone: every "expect" is what the
sources say should happen, so a deviation is information, not necessarily a bug in this list.

The order matters. Each stage is only worth looking at once the one before it passes, and every stage
ends with where to look if it fails.

## 0. Before flashing anything

- Back up `boot_a` and, to be safe, `boot_b`, `vendor_boot_a`, `dtbo_a` and `vbmeta_a`. Only `boot_a` is
  overwritten by this port, but a known-good set makes every later step reversible.
- `fastboot getvar current-slot` - the port flashes the *current* slot. Boot images are written to
  `boot_a`, the rootfs to `super` (this erases Android data).
- Know the way back **before** you need it: `fastboot flash boot_a <backup boot.img>` restores Android.
  If the phone no longer reaches fastboot at all, the Spreadtrum download mode with `spd_dump` is the
  fallback (your Termux setup).
- U-Boot gets the screen as a console (`CONFIG_VIDEO`, simple framebuffer at `0x9e000000`) and speaks
  **fastboot over USB** (`CONFIG_USB_FUNCTION_FASTBOOT`), so a USB cable is enough for the first
  stages - a UART is nice to have (`serial1`, 115200 8N1, the stock console) but not required.

## 1. U-Boot starts

Expect: after the bootloader hands over, the screen shows U-Boot's text console (white on black) and
the board model; a USB host sees a fastboot device if you interrupt autoboot.

If nothing at all appears (stays on the vendor logo, or reboots into Android):
- the `boot_a` image is not accepted - header version 4 and the payload are set in `deviceinfo`
  (`--header_version 4`, `u-boot.bin` as payload); compare with what `unpackbootimg` says about the
  stock image;
- **the memory node.** It must be the 4 GiB window (`0x0 0x80000000 0x0 0xfffff000`); the earlier 8 GiB
  value would relocate U-Boot above the end of DRAM. That is fixed in `uboot/dts` and confirmed in the
  built artifact: `u-boot.bin` from CI carries the DTB (FDT magic at `0x6ae38`) and that DTB's memory
  node is the 4 GiB one, so this is only worth re-checking if you build U-Boot yourself.

## 2. Storage

In the U-Boot console:

```
mmc list
mmc dev 3        # the eMMC is sdio3; the index depends on the aliases, find it with mmc list
part list mmc 3
```

Expect the stock partition table with `super` and the `pmOS_boot` / `pmOS_root` contents after flashing.
- **eMMC not found or I/O errors:** bus width and timing. The DTS says 8-bit, HS400es/HS200 values from the
  vendor tree. Try forcing a lower mode first (`bus-width = <4>` or dropping `mmc-hs400-enhanced-strobe`
  and `mmc-hs200-1_8v`) - if that fixes it, the delay values are the suspect.
- **SD card not seen:** card-detect. The DTS uses `eic_sync 35` (confirmed on the stock system; the empty slot
  reads high, so the flag is ACTIVE_LOW - check with a card in). `CONFIG_MMC_BROKEN_CD` is set in U-Boot, so U-Boot itself does not care; the
  kernel does. Test with a card in and out and read `cat /sys/kernel/debug/gpio`.

## 3. Kernel starts, and how to see it

Expect extlinux to boot the kernel, and the framebuffer to show kernel messages.
- The `simple-framebuffer` node in the DTS is **disabled** (the display driver takes over). To debug
  without the display driver, set it to `okay` and disable `&dpu` and `&dsi`; you get the bootloader's
  framebuffer with plain text.
- Console: `console=ttyS1,115200n8` is in `stdout-path`.
- **Crash or reboot with nothing on screen: read `ramoops`.** The DTS reserves `ramoops@fff80000`; after a
  reboot into the stock system the last kernel log is in `/sys/fs/pstore/`. This is the best
  tool this phone gives you for a kernel that dies before the display works.

## 4. USB networking (how you will actually reach it)

Expect a USB network interface on the host (`ip link`, look for `usb0`/an `enx...` name) and SSH to
`172.16.42.1` (the postmarketOS default). This is the mainline USB gadget stack, not the vendor
`sprd_f_rndis` of the 5.4 route; check that the kernel config has the configfs gadget with a network
function enabled.
- No interface: the MUSB controller is in the wrong role. The DTS sets peripheral mode with
  `usb-role-switch` and the PHY supply `vddusb33`; check `dmesg | grep -i -E 'musb|hsphy|usb'`.
- Interface but no IP: look at the initramfs log (`pmos.debug-shell` on the kernel command line gives a
  shell on the network console).

## 5. Display

Expect `dmesg | grep -i -E 'dpu|dsi|td4160|panel'` to show the panel probing and the framebuffer
switching over, and a picture (unl0kr in the initramfs).

If the panel stays dark, in this order (both are written down in `drivers/panel-td4160-hx.c`):
1. **Reset polarity.** The driver drives the raw levels from the vendor sequence (`<1 5>, <0 5>, <1 20>`)
   on `ap_gpio 50` with the DT flag `GPIO_ACTIVE_HIGH`, so logical equals physical. If the panel never
   starts, invert the physical levels with **one** change: either flip the flag to `GPIO_ACTIVE_LOW`
   and leave the driver alone, or swap 0 and 1 in the three driver calls and leave the flag. Doing both
   cancels out.
2. **Brightness.** The init sequence ends with brightness 0 (`0x51 0x00 0x00`). If the panel is
   initialised (you may see a faint image at an angle) but looks black, write a brightness:
   `echo 1500 > /sys/class/backlight/*/brightness` (maximum is 4095). If that fixes it, the curve is the
   open point, not the panel.
3. Supplies `avdd`/`avee` (`ap_gpio 54`, `55`): a missing rail also shows as a dark but initialised panel.

## 6. Touch

Expect, in `dmesg | grep -i -E 'tcm|touch'`, a firmware load of `postmarketos/sprd/hdl_firmware_01.img`
and then `touch ready: <w>x<h>, <n> objects`. Check `/proc/bus/input/devices` for
`omnivision_tcm_touch` and `evtest` for events.

- **"cannot load postmarketos/sprd/hdl_firmware_01.img":** the `firmware-infinix-x6525` package is not
  installed, or the tarball it fetches is not published yet. Put the file under
  `/lib/firmware/postmarketos/sprd/` by hand to test.
- **"no identify report after reset":** the reset line or the interrupt. The reset is active-low
  (`ap_gpio 145`); the interrupt is level-low (`ap_gpio 16`). Probe with `cat /proc/interrupts` - the
  count should move when you touch the panel, and also right after the reset.
- **Timeouts on `CMD_ROMBOOT_DOWNLOAD`:** the download is one large SPI transfer (about 100 KB).
  Check the SPI controller's limits first (`spi-sprd-adi`/the `spi3` driver's maximum transfer size) and
  the clock (`spi-max-frequency = <8000000>`); try 4 MHz.
- **Works, then stops after the screen blanks:** a panel reset also resets the touch IC. The driver
  re-downloads when it sees the new ROM-boot IDENTIFY; if it does not, send me the `dmesg` around it.

## 7. Charging

Expect `dmesg | grep -i bq2415x` to say `chip bq24158, revision 1.0, vender code 010` and
`automode supported, waiting for events`. Then:

```
ls /sys/class/power_supply/           # bq24158-*, usb-charger-detect, sc27xx-fgu / battery
cat /sys/class/power_supply/usb-charger-detect/online          # 1 with a cable in
cat /sys/class/power_supply/usb-charger-detect/current_max     # 500000 (conservative)
cat /sys/class/power_supply/bq24158-*/status
```

- **No bq24158 message:** wrong bus or address (it must be `i2c3` at `0x6a`), or `CHARGER_BQ2415X` is
  not enabled in the kernel config.
- **`online` never becomes 1:** the VBUS pin (`pmic_eic 0`), its polarity, or `extcon-usb-gpio`
  not liking a VBUS-only configuration.
- **Detected but the battery does not charge:** `ap_gpio 115` (`charger_en`) is hogged low in the DTS,
  the level the stock system shows while charging. Check `grep 115 /sys/kernel/debug/gpio` reads `out lo`.
- The 500 mA ceiling is deliberate; raise `default-microamp` in the `usb_detect` node only after this
  works.

## What to send back

The smallest set that lets me find a problem without another round trip:

1. the screen or serial output of U-Boot (the first screenful is enough);
2. `dmesg` after the kernel starts (or `/sys/fs/pstore/*` if it died);
3. for each stage above that failed, the commands listed under it.
