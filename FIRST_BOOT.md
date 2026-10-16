# First boot of the mainline port

This is the checklist for the **mainline route** (U-Boot chainloaded from `boot_a`, then the
`linux-postmarketos-unisoc-ums9230` kernel with `dts/ums9230-infinix-x6525.dts`, root filesystem on a
microSD card). The 5.4 route has its own steps at the end of `NOTES.md`. Nothing below has been run on the phone: every "expect" is what the
sources say should happen, so a deviation is information, not necessarily a bug in this list.

The order matters. Each stage is only worth looking at once the one before it passes, and every stage
ends with where to look if it fails.

## Building the ROM

Everything the ROM needs is in this repository, and none of it waits on a merge:

```sh
cp -r pmaports/device/testing/{device-infinix-x6525,linux-postmarketos-unisoc-ums9230,u-boot-infinix-x6525,firmware-infinix-x6525} \
    <pmaports>/device/testing/
pmbootstrap init          # the device is offered under "infinix" once it is in the tree
pmbootstrap install
pmbootstrap export        # writes /tmp/postmarketOS-export/
```

`linux-postmarketos-unisoc-ums9230/` here is the kernel package with this port's eleven patches in
`source=` and its five config symbols added (the reasoning is in `pmaports/README.md`), and the
u-boot package builds from the port's fork, so the `boot.img` in the export is already this board's.

`firmware-infinix-x6525` is the touch firmware, and it belongs in that copy too: the package fetches
its tarball out of this repository, which is public, so `install` gets it and the controller has what
it needs. If it ever fails to fetch, the same file sits in `firmware/` and can be dropped into
`/lib/firmware/postmarketos/sprd/` by hand.

The rest of this file is the flash procedure and then the boot, stage by stage. Only one write goes
into the phone's own storage - U-Boot, into `boot_a`; the rootfs is written to a microSD card.

## Building it on GitHub instead

`.github/workflows/rom.yml` runs the same build on an arm64 runner — Actions → **rom** → *Run
workflow* — and leaves an artifact called `x6525-rom` with the kernel, U-Boot and the rootfs image in
it. It clones pmbootstrap and pmaports itself and copies these four packages over them, so there is
nothing to prepare and nothing to install locally. The image's user password is `x6525pmos`.

Arm64 on purpose: on x86_64 every kernel build goes through qemu-user, which turns twenty minutes
into hours. `pmbootstrap init` asks its questions on stdin and cannot run unattended, so the workflow
writes the config file init would have written and points pmbootstrap at it with `--config`.

## 0. Before flashing anything

- Back up `boot_a` and, to be safe, `boot_b`, `vendor_boot_a`, `dtbo_a` and `vbmeta_a`. Only `boot_a` is
  overwritten by this port, but a known-good set makes every later step reversible. Keep a copy *off*
  the phone as well: `boot.img.xz` in Downloads is the same image at 16 MB, and the only other copy
  lives on the device being flashed. Note that a plain reboot does **not** go back to Android once
  `boot_a` holds U-Boot - restoring the image is what does that.
- `fastboot getvar current-slot` - the port flashes the *current* slot. The only eMMC write is the
  boot image, to `boot_a`; the rootfs goes to a microSD card (see [Flashing](#flashing)), so Android
  and its data are left alone.
- Know the way back **before** you need it: `fastboot flash boot_a <backup boot.img>` restores Android.
  If the phone no longer reaches fastboot at all, the Spreadtrum download mode with `spd_dump` is the
  fallback (your Termux setup).
- U-Boot gets the screen as a console (`CONFIG_VIDEO` with the simple framebuffer at `0x9e000000`)
  and a UART one (`CONFIG_SPRD_SERIAL`, `serial1`, 115200 8N1), so a USB cable is enough for the
  first stages and a UART is optional - and now also works in the kernel: `CONFIG_SERIAL_SPRD` is on
  in the ROM's kernel config, where it used to be off and left `stdout-path` inert.
- U-Boot enumerates as a **USB fastboot device** (`CONFIG_USB_FUNCTION_FASTBOOT`), but it cannot
  flash: `CONFIG_FASTBOOT_FLASH` is off in the board defconfig (checked in the built `.config`), so
  it answers `getvar`/`reboot` and not `fastboot flash`. The way back from a U-Boot that will not
  boot is the stock bootloader's own fastboot (volume keys at power-on) or, if the phone reaches
  neither, the Spreadtrum download mode with `spd_dump`.

## Flashing

The microSD route first (see the eMMC route after it for why it may not work). Two writes: U-Boot
into the phone, the disk image onto a microSD card (2 GB or more; the image is 1.3 GB). pmbootstrap
does both natively - `--sdcard` is an alias of `--disk`, which writes to the block device instead of
producing an image file, and `flasher flash_kernel` resolves to
`fastboot flash $deviceinfo_flash_fastboot_partition_kernel`, which this port sets to `boot_a`:

```sh
pmbootstrap install --sdcard=/dev/sdX    # /dev/sdX = the card, not a partition
pmbootstrap flasher flash_kernel         # with the phone in fastboot mode
```

Building locally and doing the two writes by hand is equivalent. `<out>` is the extracted `x6525-rom`
artifact, or `/tmp/postmarketOS-export/` after `pmbootstrap export`; with the phone in fastboot mode
(`fastboot devices` lists it):

```sh
fastboot flash boot_a <out>/boot.img
dd if=<out>/infinix-x6525.img of=/dev/sdX bs=4M conv=fsync    # /dev/sdX = the card, not a partition
```

- The card is written **whole**, because the image carries its own partition table: an extended-boot
  partition holding `/extlinux/extlinux.conf`, `/vmlinuz`, `/initramfs` and the DTB, and the root
  filesystem. The initramfs finds both by the filesystem UUIDs baked into the extlinux command line
  (`pmos_boot_uuid`/`pmos_root_uuid`, written by boot-deploy from the image's own fstab), and those
  travel with a copied image, so it boots the same way from the card as it would from anything else.
- Both routes write the same bytes: `--sdcard` puts on the card exactly what `dd`-ing the exported
  image would, and `flasher flash_kernel` is the same `fastboot flash boot_a boot.img`.
- Do **not** run `pmbootstrap flasher flash_rootfs`. It would write the whole 1.36 GB disk image into
  the phone's `super` partition, and U-Boot cannot see a partition table nested inside a partition
  (`drivers/block/blk-uclass.c`: `part_create_block_devices()` returns early unless the device is
  `UCLASS_BLK`, and a partition is `UCLASS_PARTITION`). It would find no bootflow and sit at the
  U-Boot prompt - that is what the earlier procedure did.
- Nothing else on the eMMC is written: Android and its data stay where they are, and
  `fastboot flash boot_a <backup boot.img>` is the way back.
- The image is smaller than any current card, so the copy leaves the backup GPT 1 MB from the image's
  end rather than the card's. That is harmless - the kernel tolerates a smaller disk's protective MBR
  on a larger one on purpose, "to support dd'ing an image from a smaller disk to a larger disk"
  (`block/partitions/efi.c`) - and `sgdisk -e /dev/sdX` afterwards only tidies the backup copy.
- Insert the card, then plug in the USB cable **before** powering on: the initramfs brings the USB
  gadget up once, about two seconds in, and never retries (see 4).

### Flashing to the eMMC instead (recommended for a first boot)

The microSD route has an assumption nothing has tested: that U-Boot can see the card at all. The slot's
supply rails (`vddsdcore`, `vddsdio`) are LDOs of the SC2730 PMIC, and U-Boot has no PMIC or regulator
driver (`configs/infinix-x6525_defconfig` has no `DM_REGULATOR`/`DM_PMIC`; `sdhci-sprd.c` handles no
supplies). In the stock dump both rails are *disabled* while no card is in use, so unless the stock
bootloader leaves them on, the slot is unpowered when U-Boot looks and the boot ends at the prompt. The
eMMC has no such problem: its rail is on from power-up, and it is what U-Boot already reads.

U-Boot cannot read a partition table nested inside an eMMC partition, so the whole-disk image cannot go
there. The `rom` workflow therefore also cuts it into its two filesystems (`tools/split-disk-image.py`),
which are flashed into two eMMC partitions of their own:

```sh
fastboot getvar partition-size:cache          # must be >= the size of pmos-boot-fs.img (256 MiB)
fastboot getvar partition-size:userdata       # must be >= the size of pmos-root-fs.img
fastboot flash boot_a  <out>/boot.img         # as before
fastboot flash cache    <out>/pmos-boot-fs.img    # pmOS_boot: extlinux.conf, kernel, initramfs, DTB
fastboot flash userdata <out>/pmos-root-fs.img    # pmOS_root
```

- This overwrites `cache` and `userdata`. Android's *system* (`super`) is untouched, but its data is gone:
  after restoring `boot_a` Android will find an unrecognised `userdata` and have to format it, so it
  starts like a fresh install (`fastboot -w` from the stock bootloader does the same explicitly). Back up
  what you need first. Do not use `persist`, `metadata`, `misc`, `tkv_*` or any of the `*_a`/`*_b` pairs for
  this - `persist` holds the device's calibration.
- fastboot splits a large raw image into chunks by itself, so the 1.3 GB root image needs no `sparse`
  conversion on your side.
- The filesystems keep their UUIDs and labels, so the extlinux command line (`pmos_boot_uuid`,
  `pmos_root_uuid`) finds them wherever they were written. Check with `file -s` on the two images: they must
  be ext2/4 filesystems, not a disk with a table.
- If `cache` is smaller than the boot image, use another expendable partition for `pmOS_boot` rather than
  shrinking anything: U-Boot scans every partition of the eMMC for a bootflow, so the name does not
  matter.

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
mmc dev 0        # the board device tree aliases the eMMC (sdio3) as mmc0, so it is device 0
part list mmc 0  # if mmc list shows something else first, use the number it prints
```

Expect two devices. The eMMC still carries Android's stock partition table - this route does not
touch it - while the microSD is the pmOS one: an extended-boot partition holding `/extlinux`, and
the Linux root. `bootcmd` is `bootflow scan -lb mmc` (from `board/unisoc/ums9230/ums9230.env`), so
U-Boot looks on both and boots the card.
- **The eMMC is slow (DDR52, tens of MB/s):** expected, not a fault. `sdhci-sprd` keeps
  `SDHCI_QUIRK2_BROKEN_HS200` set for `sprd,sdhci-r11`, and the core clears `MMC_CAP2_HS200` for it -
  HS400 is gated behind HS200, so the HS200/HS400 flags the DTS declares never take effect.
- **eMMC not found or I/O errors:** the DTS now carries the device's own values (8-bit, the speed
  flags, all five `sprd,phy-delay-*` sets, and no `vqmmc-supply` - `vddsdio`, which the port used to
  name here, is the microSD slot's IO rail), so the remaining suspect is the delay *tuning*: drop
  `sprd,phy-delay-mmc-ddr52` to fall back to the driver's defaults, or force `bus-width = <4>`, and
  see if the errors move.
- **SD card not seen:** card-detect. The DTS uses `eic_sync 35` (confirmed on the stock system; the empty slot
  reads high, so the flag is ACTIVE_LOW - check with a card in). `CONFIG_MMC_BROKEN_CD` is set in U-Boot, so U-Boot itself does not care; the
  kernel does. Test with a card in and out and read `cat /sys/kernel/debug/gpio`.
  If *U-Boot* does not list the card at all in `mmc list`, the slot's rails are the suspect: U-Boot has no
  driver for this PMIC's regulators and `sdhci-sprd.c` touches no supplies, so it can only use what the stock
  bootloader left powered - the reeder's board is in exactly the same position, so this is the design, not a
  fault in the board files. The kernel powers the slot itself, but a bootflow cannot start from a card U-Boot
  cannot read: report it. The eMMC does not share this risk (Android boots from it; its rails are already on).

## 3. Kernel starts, and how to see it

Expect extlinux to boot the kernel, and the framebuffer to show kernel messages. The kernel command
line carries `loglevel=7` (the device package's `kernel-cmdline.conf`; the distro config ships
`quiet`, and the later `loglevel=` is the one that counts), so the console is not filtered.
- The `simple-framebuffer` node in the DTS is **enabled** for the first boot: the bootloader leaves the
  panel scanning out `0x9e000000`, and `DRM_SIMPLEDRM` + fbcon turn that into a text console, so kernel
  messages are visible even if the DPU/DSI/panel stack never probes. If the real display stack works,
  the two coexist (the picture may go stale when the DPU takes over); then set the node to `disabled`.
  To rule the display driver out entirely, also disable `&dpu` and `&dsi`.
- Console: the device package's `kernel-cmdline.conf` names `console=tty0 console=ttyS1,115200n8` (without a
  `console=tty0` the kernel prints only to the UART when `stdout-path` is set, so the screen would stay silent;
  naming a console also turns `stdout-path` off, hence the UART is named too), `plymouth.enable=0` and `nosplash`. The UART is in `stdout-path`, and `CONFIG_SERIAL_SPRD=y` in the ROM's
  kernel config (it was off before, which left the property inert) makes it a real console.
- **Crash or reboot with nothing on screen: read `ramoops`.** The DTS reserves `ramoops@fff80000`, and
  `CONFIG_PSTORE_RAM=y` is set, so the last kernel log survives in `/sys/fs/pstore/` for the next boot
  to read - including a boot that only gets as far as the initramfs, whose debug shell mounts pstore
  first (see 9). This is the best tool this phone gives you for a kernel that dies before the display
  works.

- **Reboots about 12 seconds after the kernel starts: the watchdog.** The stock command line carries
  `androidboot.wdten=e551`, and `sprd_wdt` (DT `timeout-sec = <12>`) used not to notice a counter the
  bootloader had already started, so nothing fed it until userspace opened `/dev/watchdog`. Patch 11 marks
  it running when the enable bit is set at probe, so the core feeds it. If the reboot loop persists with
  that patch in, it is a different watchdog (the PMIC's has no mainline driver).

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
  installed. Put `firmware/hdl_firmware_01.img` from this repository under
  `/lib/firmware/postmarketos/sprd/` by hand to test.
- **"no identify report after reset":** the reset line or the interrupt. The reset is active-low
  (`ap_gpio 145`); the interrupt is level-low on `eic_async` 16, which is what the running system's
  own tree carries - the vendor overlay's `ap_gpio 16` is a different line, and on it the controller
  never sees the first IDENTIFY report. Probe with `cat /proc/interrupts` - the count should move
  when you touch the panel, and also right after the reset.
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

## 8. Sensors

Expect only the proximity sensor: `dmesg | grep -i vl53` and an IIO device under `/sys/bus/iio/devices/`
(`cat in_distance_raw` with a hand over the top of the phone). It is the VL53L0X the vendor overlay
names as `0x52` on `i2c4` (the 8-bit form; the node uses the 7-bit `0x29`). XSHUT and the interrupt are
`ap_gpio` 168 and 169, taken from the overlay's bare numbers (its `interrupts` property uses 169 with `ap_gpio`
as parent, which is chip-local) - not confirmed on hardware. If it does not probe, suspect XSHUT first. The
Smart 8 may not even carry the part - the overlay is shared - so a probe failure here is not a bug in the port.

The accelerometer and ambient-light sensor are not here: the vendor kernel reaches them through
`sprd,sensor-hub`, a coprocessor with no mainline driver. Auto-rotate and auto-brightness will not work.

## 9. When it does not boot

The initramfs has two levers on keys you already have. Both are checked *after* USB networking is up,
and both work here because `evdev` is in the initramfs (pmOS ships it in `00-default.modules`) and
`CONFIG_KEYBOARD_GPIO=y`, so the volume keys are readable that early:

- **Hold volume-down while booting** - the debug shell. It runs over the USB network that is already
  configured and mounts `/sys/fs/pstore` before it starts, so a panic `ramoops` captured is readable
  there even when the rootfs never mounted. In images built after this change the initramfs also
  carries the vibrator (`modules-initfs`), so the shell announces itself by buzzing; before that it
  hides the splash instead.
- **Hold volume-up while booting** - refuse to continue and dump the logs.

If neither key does anything, the keys themselves are the suspect, not the lever.

If **U-Boot** finds no bootflow (card missing or unreadable), there is no way to type at its prompt:
it has no `stdin`, so the phone sits there silently. Hold the power key to turn it off, insert the
card, and try again - or leave the card out and go to the stock fastboot with the volume keys, where
`fastboot flash boot_a` still works.

The lever that does not depend on the keys is `pmos.debug-shell` in the card's
`/extlinux/extlinux.conf`: mount the card on any PC, add it to the `append` line, put the card back.
The initramfs then opens a shell unconditionally - and stops there until `pmos_continue_boot` is run
in it, which is why it is not on the default command line: if USB never comes up, a boot carrying it
would wait forever at a shell nobody can reach.

## What to send back

The smallest set that lets me find a problem without another round trip:

1. the screen or serial output of U-Boot (the first screenful is enough);
2. `dmesg` after the kernel starts (or `/sys/fs/pstore/*` if it died);
3. for each stage above that failed, the commands listed under it.
