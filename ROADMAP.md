# What is still missing

This is the reference inventory of everything this port does not have yet, so a later session does
not have to rediscover it. It is deliberately separate from [BRING_UP_CHECKLIST.md](BRING_UP_CHECKLIST.md):
the checklist is *how to test or bring up* a feature, this is *what is not there yet*.

Status words used below:

- **in tree** - the code, device tree and packaging are in this repository; it may still be untested
  on the phone (the hardware status is called out separately).
- **untested** - in tree, but nothing has run it on the phone yet. The test commands are linked.
- **missing** - no code exists in the port (or mainline) for it.
- **blocked** - a prerequisite outside this repository is needed.
- **deferred** - the user asked to leave it until the camera, connectivity and sensors are done.

Everything is eMMC: the stock cmdline says `sprdboot.flash=emmc` and the storage is on `sdio3`
(`NOTES.md`). The X6525 also shipped in a UFS variant; this port and its U-Boot have no UFS support,
so it does not boot there. That is a hardware-variant limitation, not an unfinished driver.

## Camera

| Part | Status | Detail |
|---|---|---|
| Rear Samsung S5K3L6 (slot 0) | in tree, untested | `drivers/media/i2c/s5k3l6.c` (kernel patch 0014), node on i2c1 0x2d and the 4-lane camsys port (0015). Vendor register tables, 24 MHz, 4 lanes, RAW10. Needs frames, not just a probe - see checklist 5.1. |
| Front OmniVision OV8856 (slot 1) | in tree, untested | Mainline `ov8856` driver, node on i2c0 0x10, 2-lane M port (kernel patch 0020). Runs at 19.2 MHz because the mainline driver has no 24 MHz tables; the vendor library uses 24 MHz. Power-down (ap_gpio 46) is held low by a gpio-hog because the driver has no power-down support. |
| Flash (OCP8137 / AW36515) | missing | The live tree has both at i2c5 0x63/0x64, torch enable on ap_gpio 137 (confirmed from the stock device tree; exposed as the `white:flash` LED), other flash pins unconfirmed, sync on 121. No mainline driver for the I2C parts, so no flash for stills and no flash for stills. |
| VCM / autofocus | missing | The front socket also has `vddcammot`; the rear lens's focus motor has no mainline driver in this tree. Fixed-focus until then. |
| Camera EEPROM/OTP | missing | The unit's `/mnt/vendor/productinfo/otpdata` is empty, so there is no calibration data to read for this unit anyway. |
| Camera userspace | missing | The mainline sprd stack exposes raw Bayer and the ISP blocks over V4L2, but there is no libcamera pipeline handler, no 3A and no application. First milestone is raw frames; a usable camera is a userspace project. |
| Second rear lens | not applicable | Slot 2 reports `fakeserial`: it is a decorative lens. `sensor-main2` in the live tree is the fake serial device, not a sensor. |

## Connectivity

| Part | Status | Detail |
|---|---|---|
| Wi-Fi | in tree, hardware-tested per checklist 2 | Mainline `sc23xx_wlan` + `sprd_wcn`; `wcnmodem.bin`, `wifi_board_config.bin` packaged. |
| Bluetooth | in tree, fixed (patches 0031, 0032) | `btsprdsipc` and config blobs packaged. Fixed SIPC sbuf probe race (patch 0031) and btsprdsipc drvdata ordering (patch 0032). `x6525-prodnv-mac.service` persists `btmac.txt` and `wifimac.txt` to `prodnv` for U-Boot preboot, falling back to patch 0013 random BD address if absent. |
| GNSS | in tree, untested | `gnssmodem.bin` packaged; `sprd_wcn` GNSS child, `drivers/gnss/sprd.c`, `/dev/gnss0`. The `pm_gnss` SIPC channel lives under pmsys, so the pmsys co-processor has to run: `pm_bootcode.bin` is now packaged (firmware pkgrel 6) and `x6525-pmsys.service` copies `pm_sys.bin` out of `pm_sys_a` at boot. No gpsd/geoclue is installed by default. |
| Cellular modem | in tree, never brought up | `sprd_modem` and the six images exist; `x6525-modem-nv.service` extracts them from the unit's own partitions (the NV carries the IMEI and is not published). What is unknown is whether the Unisoc LTE stack initialises on mainline at all: SIM rails are not described in the DT, and no modem has reached `running` yet. |
| BC1.2 / charger type detection | missing | The SC2730 does the detection in the stock stack (`sprd_bc1p2`); mainline has no driver. A VBUS GPIO supply is used instead, so charging is limited to 500 mA. |
| FM radio | missing | The WCN SIPC has an `fm` channel, but there is no mainline FM driver or userspace. |
| NFC | not fitted | The live tree has a `sec-nfc@27` node on i2c2, but this unit's hardware list does not show an NFC part in use. Treat as absent. |

## Sensors

| Part | Status | Detail |
|---|---|---|
| Sensor hub (accelerometer, magnetometer, light and proximity, virtual gyro) | in tree, untested | Mainline `sprd_shub` and the five IIO drivers are `=m`. They bind to the `pm_shub` SIPC channel, which needs pmsys running - the same service as GNSS. The pmsys image's own strings name the parts it drives: **SC7A20E** accelerometer, **MMC5603** magnetometer and **LS9801** light/proximity, plus a **virtual gyro** (there is no physical gyro). Calibration data from the stock `persist` partition is not wired up. |
| VL53L0X time-of-flight | in tree, unverified | Node on i2c4, `st,vl53l0x`, `reg = <0x29>`, XSHUT ap_gpio 168, interrupt 169. The stock node used reg 0x52 (its 8-bit form) and a vendor driver; if the part does not probe, the address and XSHUT sequencing are the first suspects. |
| Fingerprint | missing | The stock system binds a Goodix sensor (`gf-keys`). There is no mainline driver for it, and none is planned here. |
| Thermal zones | in tree | `board-thermal`, `pa-thermal`, `chg-thermal` with the stock NTC tables; no trips or polling, matching the stock zones. |

## Storage, display, audio, USB and power

- **Storage**: eMMC root and the microSD slot work; the eMMC write cache is disabled at boot
  (`x6525-emmc-cacheoff.service`) because the unit loses power uncleanly. UFS is not supported (see
  the top of this file). eMMC/SD PHY timing has not been tuned beyond what the bootloader leaves.
- **Display**: the TD4160 HX panel driver exposes 60.03 Hz and 90.05 Hz modes. 60.03 Hz is the
  board DT's `native-mode` and is preferred again (patch 0023); patch 0019's 90 Hz timing remains
  selectable but is not the boot default. Making it preferred caused a black screen on hardware:
  the bootloader logo stayed while the kernel ran, i.e. the 90 Hz modeset was not accepted. Brightness
  is DCS, not PWM. The panel reset polarity is the first suspect if a future panel stays dark.
- **Audio**: the SC2730 codec and the speaker amp (`ap_gpio 113`) are described; playback is the
  current path. Voice-call audio depends on the modem and is untested. Headset detection/mic routing
  is not described on mainline.
- **USB**: networking (the login path) is in tree. OTG host mode now has the bq2415x boost as a
  `vbus-supply` (patches 0016/0017) but has not been tested with a keyboard/stick. The stock system's
  "unknown USB mode" notification is not a mainline message; if the port shows a similar problem,
  the Type-C/role-switch path is where to look. USB PD is present through `sc27xx_pd`/`tcpm`, but
  only the charger role has been exercised.
- **Charging**: bq24158 driver, VBUS detection, the USB-detection supply, and the charger-enable hog
  are in tree. JEITA tables and BC1.2 are not. Charging current is capped at 500 mA until BC1.2.

## Performance and the storage variant

**In tree now:**

- **CPU DVFS** - `sprd-cpufreq-v2` with the chip's own DVFS bins from the NVMEM cells, enabled in the
  board DTS (`&cpufreq { sprd,soc-version = <0x36303654>; status = "okay"; }`).
- **CPU thermal throttling** - the SoC's `cputop0`/`ank*` zones already have 70 C passive trips and
  cpufreq cooling maps in the mainline dtsi.
- **GPU thermal throttling** - patch 0021 gives the `gpu-thermal` zone a 70 C passive trip and a
  devfreq cooling map to `&gpu` (Panfrost registers the cooling device). Before this the zone only
  reported; the GPU never throttled.
- **Storage PHY delays** - the board DTS carries the stock values for eMMC (HS/HS200/HS400/ES) and
  microSD (legacy/HS/SDR50/SDR104).
- **HS200/HS400 test knob** - patch 0022 adds `sdhci_sprd.enable_hs200=1`; see the test below.

**Still open:**

- **GPU 650 MHz** - the top step the stock driver allows on T606 (it disables its 768 and 850 MHz
  entries; the part is capped at GPLL = 650 MHz). The OPP table now has 650 MHz @ 0.80 V, with the
  gpu node programming GPLL to 650 MHz at probe, because the mainline composite GPU clock does not
  pass rate requests to its parents. Untested on hardware: check `cat
  /sys/class/devfreq/23100000.gpu/available_frequencies` and `/sys/kernel/debug/clk/gpll/clk_rate`.
  850 MHz stays out (disabled by the stock driver itself).
- **eMMC link speed** - `sdhci_sprd_pdata` sets `SDHCI_QUIRK2_BROKEN_HS200` for every r11
  controller, so the core clears `MMC_CAP2_HS200` and the link stays at DDR52 (HS400 is gated behind
  HS200), although the stock kernel runs this part at HS400. The opt-in knob exists to test whether
  the quirk is unnecessary on UMS9230; if it is, the quirk should be narrowed by compatible (and the
  knob removed) after it has run on hardware. The eMMC is the root filesystem, so this is
  deliberately not the default.
- **Suspend/resume** - the firmware's PSCI is 0.2 (`compatible = "arm,psci-0.2"`), which has no
  SYSTEM_SUSPEND; the vendor suspends through the PM co-processor, not PSCI. CPU idle
  (core power-down, `arm,psci-suspend-param = <0x10000>`) works. `systemctl suspend` is therefore
  expected to fail or only freeze; s2ram needs a pmsys suspend driver that does not exist yet.

**UFS (the other storage variant):** not fitted on this eMMC unit, and the stock tree disables its
`ufs@20200000` node too. The mainline kernel already builds `CONFIG_SCSI_UFS_SPRD=y` and the dtsi
has the node disabled; the reeder enables it with `vcc-supply = <&vddemmccore>`. To support a UFS
unit, U-Boot needs `CMD_UFS`/`SCSI`/`UFS`/`UFS_SPRD_UMS9230` back in its defconfig, the board DTS
needs the UFS node enabled (and the eMMC node likely disabled), and the bootcmd must scan `scsi` as
well as `mmc`. None of that can be tested here, and enabling it unconditionally on an eMMC unit
would share `vddemmccore` with the rootfs device, so it stays off.

## Upstreaming

- The kernel series (now 22 patches in `patches/upstream/`) is cut against the
  `v7.2-rc6-ums9230-0` tag and has not been sent. Patch 22 is explicitly not for submission. The
  two U-Boot patches have not been sent either. `NOTES.md` explains where each series should go
  (kernel: maintainer by mail/issue, not a PR against the stale branch; U-Boot: PR from the fork
  branch).
- The fork branches in `NOTES.md` are force-updated when the series changes, so
  `git format-patch` from them remains the source of truth for the patch files.

## Hardware-test queue

In the order the current work needs them:

1. **Camera** - both sensors probe, then raw frames:
   `dmesg | grep -iE 's5k3l6|ov8856|camsys'`, `media-ctl -p`, `v4l2-ctl --list-devices`, then the
   test-pattern and stream commands in checklist 5.1.
2. **pmsys, GNSS and the sensor hub** - `journalctl -u x6525-pmsys`, `cat /sys/class/remoteproc/*/state`,
   `ls -l /dev/gnss0`, `ls /sys/bus/iio/devices`, then `gpsd -n /dev/gnss0` outdoors (checklist 5.3).
3. **OTG host** - a keyboard or stick on the port, `dmesg | grep -i usb`, `lsusb`
   (checklist 4.5).
4. **Cellular** - `mmcli -L`, `mmcli -m any`, the remoteproc state and the service log
   (checklist 5.2).
5. **90 Hz** - `modetest -M sprd-drm` / the compositor's refresh-rate setting (checklist 3.0).
6. **MACs** - `printenv bdaddr wifiaddr` at the U-Boot prompt, then `ip link` and
   `bluetoothctl show` on pmOS; if the variables are empty, check the `prodnv` files (checklist 2.1).
7. **Performance** - the GPU thermal trip and cooling device, the HS200 opt-in test, and the
   suspend expectations (checklist 7.1-7.3).
