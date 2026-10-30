# Bring-up checklist: touch, Wi-Fi, then GUI

What to run after flashing a ROM build, and what each result means. Work in this order: each step
needs the one before it. Everything here runs in the initramfs debug shell (USB serial on the host,
`minicom -D /dev/ttyACM0`, or telnet `172.16.42.1`) or over SSH once booted.

Flash `boot_a`, `cache` and `userdata` from the **same** ROM run. Keep the stock `boot.img` backup off
the phone (see FIRST_BOOT.md, "Recovery").

## 1. Touch

Status on 2026-10-20: the controller answers. The driver downloads the firmware, the SPI path works,
and it registers the input device:

```
input: omnivision_tcm_touch as .../spi0.0/input/input2
omnivision_tcm_spi spi0.0: touch ready: 5759x12895, 5 objects, config id
```

That boot had it as `event2`. The interrupt is not the blocker: `/proc/interrupts` shows
`sprd-eic 16 Level ovt-tcm`, and its count went 1050 -> 1166 -> 1610 across the session, so the
controller asserts and the driver's threaded handler runs. buffyboard accepts the device as well:
started with `-v` it logs `New input device: omnivision_tcm_touch`.

The event node delivers as well: the captured stream decodes as a complete touch - tracking id,
position, pressure, `BTN_TOUCH` and `SYN_REPORT` (1.7). The captured space-bar tap then showed why
the keyboard ignored it: the driver asked for 12-bit position fields, and raw Y above 4095 wrapped
modulo 4096, so a tap could never land in the keyboard strip. That is fixed in the driver (1.7); the
next build is the test.

An IRQ count that also rises while nobody touches would mean the controller keeps sending reports
(or re-asserts the line); the event stream says which of them reach userspace.

### 1.1 The test

In the debug shell:

```sh
ls /dev/input
grep -A4 omnivision /proc/bus/input/devices
dmesg | grep -iE "tcm|ovt|vddldo0|regulator"
grep -iE "ovt-tcm|eic" /proc/interrupts

# let the command pick the event node from the Handlers= line, so a literal
# "eventN" cannot be read by mistake
node=$(grep -A4 -i omnivision /proc/bus/input/devices |
       sed -n 's/.*Handlers=\(event[0-9]*\).*/\1/p')
echo "reading /dev/input/$node"                     # must be event<number>, not empty
timeout 10 cat "/dev/input/$node" | od -An -tx1 -v  # touch the screen during these 10 s

grep -iE "ovt-tcm|eic" /proc/interrupts
```

`od` cannot read an evdev node by itself: it reads 16-byte blocks, and evdev rejects any read
shorter than one `struct input_event` (24 bytes on aarch64) with `EINVAL` - the symptom is
`od: /dev/input/event2: read error`. Pipe through `cat`, which reads in large blocks.

`buffyboard` (the on-screen keyboard) is not the test: it can ignore a device that appeared after it
started. The `od` output is the test. Replace `eventN` with the number from `Handlers=eventN` -
`eventN` as written is not a file. (`od` is a busybox applet; the rootfs also has `/usr/bin/hexdump`.)

The IRQ action is registered as **`ovt-tcm`** (`devm_request_threaded_irq(..., "ovt-tcm", ...)` in
`drivers/ovt-tcm-spi.c`); `omnivision` is the input device's name, not the interrupt's. A
`grep omnivision /proc/interrupts` that prints nothing therefore proves nothing.

### 1.2 If events appear (touch works)

1. The driver and the hardware are fine. If `buffyboard` still ignores the screen, restart it:
   `killall buffyboard; buffyboard &`. If that makes the keyboard work, the cause is start order
   (`buffyboard` starts before the module has created the device). Tell the maintainer; the fix is in the
   initramfs, not the driver.
2. Run `pmos_continue_boot`, log in over SSH, and run `sudo sh phone-audit.sh` (from `tools/`). The touch
   lines should be PASS, including the line that checks the rail is still on after 60 s.
3. Wait two minutes and run the `hexdump` again. Touch dying after ~30-40 s means `vddldo0` was switched
   off: check `cat /sys/class/regulator/*/name` against `.../state` and that the cmdline still has
   `regulator_ignore_unused`.
4. Save the numbers: `dmesg | grep "touch ready"` (the stock reports `5759x12895`, 8 x the panel's pixels;
   the compositor scales it).
5. Move on to section 2.

### 1.3 If no events appear

Find which row matches. `touch ready` is the driver's line printed after the chip has booted and its
report config is set.

| What you see | Meaning | Next |
|---|---|---|
| No `touch ready` line, firmware error (`firmware`, `-2`) | the HDL image is missing | `ls /lib/firmware/postmarketos/sprd/` in the debug shell (it must be in the initramfs) and `ls /usr/share/mkinitfs/files/`. Send both. |
| No `touch ready`, SPI errors or repeated `Incorrect header marker` | chip not answering | one such line at the first read is normal (stock prints it too). Repeated means reset or rail: send the `dmesg` lines and `cat /sys/class/regulator/*/name`. |
| `touch ready` but the interrupt count is 0 and stays 0 when touching | the interrupt line is not arriving | the stock system uses `eic_async` line 16, level-low, as `omnivision_tcm`, and so do we. Send `/proc/interrupts` in full and `dmesg \| grep -i eic`. |
| `touch ready`, interrupt count rises, but `hexdump` is empty | the driver reads reports but does not deliver them | send the full `dmesg` and `cat /proc/bus/input/devices`. The driver has no extra debug output, so this case needs a debug build from the maintainer. |
| `touch ready` appears, then touch stops after 30-40 s | the 2.8 V rail was cut | `vddldo0` must be always-on (device tree) and `regulator_ignore_unused` must be on the cmdline. Send `cat /proc/cmdline`. |

Always send, whichever row: the output of the 1.1 commands, and the first 100 lines of `dmesg`.

### 1.4 Meanwhile, without touch

The phone is fully usable from the host: serial console `minicom -D /dev/ttyACM0`, and SSH
(`ssh user@172.16.42.1`, password `x6525pmos`) after boot. Touch is only needed for the GUI.

#### After `pmos_continue_boot`

The USB ACM console (`/dev/ttyACM0`) and telnet are removed by design at this point: the initramfs
removes the ACM function before `switch_root`, and telnetd stops. The NCM link re-enumerates, often
under the next free name. A line like `printk: legacy console [tty0] disabled` is the kernel's
console handover notice, not a failure.

The rootfs is up when SSH answers. The image has systemd, `sshd`, `getty@tty1` and
`buffyboard.service` enabled, so:

```sh
# host (A01 Core), after pmos_continue_boot; wait ~60 s for the gadget
ip -br link                     # the NCM interface, possibly usb1 or higher now
ip link set usbN up             # usbN = the name ip -br link printed (usb0, usb1, ...)
ip addr add 172.16.42.2/24 dev usbN
ip rule add from all to 172.16.42.0/24 lookup main pref 100
ip rule add from 172.16.42.0/24 lookup main pref 100
ssh user@172.16.42.1            # password x6525pmos
```

If SSH does not answer a minute after `pmos_continue_boot`, it is a real boot failure: capture the
last screen lines (a photo is fine) and, if available, the UART output on `ttyS1` (115200 8N1).

**`cache` and `userdata` must come from the same run.** `extlinux.conf` on `cache` carries
`pmos_root_uuid`, and the initramfs mounts the root only by that UUID. A cache-only flash (the usual
way to try a new kernel) points at a filesystem UUID that is not on the phone, and the boot stops
right after the console handover with no further error on screen. Flash the matching rootfs:

```sh
fastboot flash userdata pmos-root-fs.img   # same run as the cache you flashed
```

The same applies in reverse: a new userdata with an old cache has a UUID the old extlinux does not
name. Both files come out of one ROM artifact; flash them together.

Check it in the debug shell before continuing. The boot filesystem is not mounted there, but the
UUIDs U-Boot got from extlinux are in the kernel command line:

```sh
tr ' ' '\n' < /proc/cmdline | grep -E 'pmos_(root|boot)_uuid'
blkid
```

The `pmos_root_uuid` value must appear in `blkid`'s output (on `mmcblk0p73`, the `userdata`
partition). If it does not, the rootfs on the phone is from a different build, and
`pmos_continue_boot` has nothing to mount. To read extlinux itself, mount the boot filesystem by
its label: `mkdir -p /mnt; mount -o ro "$(blkid -L pmOS_boot)" /mnt; cat /mnt/extlinux/extlinux.conf`.

If the UUIDs match and the boot still stops, walk the same steps by hand. Each prints, so the one
that errors or never returns is the step `pmos_continue_boot` dies in:

```sh
root=$(blkid -L pmOS_root); echo "root=$root"
e2fsck -p "$root"; echo "fsck=$?"
resize2fs "$root"; echo "resize=$?"
mkdir -p /mnt; mount -t ext4 -o rw "$root" /mnt; echo "mount=$?"
cat /mnt/etc/os-release; umount /mnt
```

`resize2fs` growing the freshly flashed 907 MB filesystem to the 110 GiB `userdata` partition is
the expected long step; if it is the one that hangs, let it run and note how long. If all four
succeed quickly, the stop is after the mount (systemd or `switch_root`), and the UART on `ttyS1`
is the next place to look.

#### Boot straight through (no debug shell)

Removing the ACM function and re-binding the UDC happens only in the debug-shell continue path.
Booting without `pmos.debug-shell` skips it entirely: the NCM link is set up once and never torn
down, so there is no `ttyGS0` to disable and no gadget swap. Patch the boot filesystem with the
same image you are flashing, then flash it:

```sh
sh tools/patch-cmdline.sh --remove pmos-boot-fs.img pmos.debug-shell
fastboot flash cache pmos-boot-fs.img
fastboot flash userdata pmos-root-fs.img   # only if the phone's userdata is another run's
```

Both files must come from one ROM run; check before flashing that the rootfs UUID is the one the
patched extlinux names:

```sh
blkid -p pmos-root-fs.img                    # UUID= must match...
sh tools/patch-cmdline.sh pmos-boot-fs.img   # ...pmos_root_uuid= on the append line
```

The tool keeps the unpatched copy as `pmos-boot-fs.img.orig`; add the option back with
`sh tools/patch-cmdline.sh pmos-boot-fs.img pmos.debug-shell` when the boot works. With no debug
shell, hold **volume-down** during boot to get one (the initramfs `check_keys` path) if it fails.

#### `Filesystem needs manual repair (fsck)` at boot

The initramfs runs `e2fsck -p` (preen) on the root filesystem every boot. If preen finds an
inconsistency it cannot fix, the boot stops with:

```
root: Inode NNNN seems to contain a garbage ...
ERROR: UNEXPECTED INCONSISTENCY: RUN fsck MANUALLY
Filesystem needs manual repair (fsck) (/dev/mmcblk0p73)
```

Press **Volume-Up** or **Left-Shift** at that screen for the debug shell (the message says so), then
repair the filesystem. **Make sure it is not mounted first** - a failed boot can leave `/sysroot`
mounted, and `e2fsck` on a mounted filesystem damages it further (a "clean" run can then leave the
system unable to complete a login):

```sh
mountpoint -q /sysroot && umount /sysroot
e2fsck -fy /dev/mmcblk0p73
sync
reboot -f
```

`-y` answers yes to every fix; on the 110 GiB `userdata` filesystem it can take several minutes - let
it finish. The usual trigger is a hard power-cycle: the first boot after a flash grows the
filesystem from the image's 907 MB to the partition size, and cutting power during that (or during
any write) loses metadata the journal cannot fully replay. While bringing up, reboot with
`sudo reboot` / `sudo poweroff` and let the first boot reach the login prompt before power-cycling.

If the console login accepts the password and then returns to the prompt (or the boot drops into
recovery mode), the on-disk system was damaged - either by the corruption itself or by an fsck run
on a mounted filesystem. The clean recovery is to reflash `userdata` from the same artifact and let
the first boot finish:

```sh
fastboot flash userdata pmos-root-fs.img   # same run as the cache
```

If it keeps happening without power cuts, collect the storage-side evidence:

```sh
sudo dmesg | grep -iE 'mmc0|sdhci|I/O error|ext4|jbd2' | tail -60
cat /sys/block/mmcblk0/queue/write_cache      # should stay 'write back' - barriers; the card cache is off instead
cat /sys/class/mmc_host/mmc0/mmc0:*/speed 2>/dev/null
cat /sys/class/mmc_host/mmc0/mmc0:*/name 2>/dev/null
mount | grep ' / '
journalctl -b -p err --no-pager | tail -40
```

The device package disables the **eMMC's own write-back cache** at the EXT_CSD level
(`x6525-emmc-cacheoff.service`, `mmc cache disable /dev/mmcblk0`, run every boot because
`CACHE_CTRL` is not persistent). A second unit, `x6525-emmc-flush.service`, runs
`mmc cache flush` as an `ExecStop` during shutdown, after the normal services have stopped and
while the root is still writable - so a clean Power Off also flushes even if the card refused the
disable, or if something wrote through the cache after boot. This is deliberately not the block queue's `write_cache` flag:
setting that to `write through` also stops the kernel from sending flush barriers while the card
still caches writes. With the card cache off, a forced power-off loses at most the writes in
flight, and the ext4 journal can replay; write throughput is the price. The service runs before
`sysinit.target`, i.e. after the initramfs's own fsck/resize - the first boot after a flash must
still not be cut short.

**Images up to device package pkgrel 18 did not run either unit**, even though both `.service`
files were in the image: the build log says
`Removed '/etc/systemd/system/sysinit.target.wants/x6525-emmc-cacheoff.service'` - pmOS's
`systemd-apk-trigger` runs `systemctl preset` for every newly installed unit, and
`99-default.preset` is `disable *`. Symlinks created by the package are removed again; only a
preset rule survives. pkgrel 19 ships
`/usr/lib/systemd/system-preset/90-infinix-x6525.preset` for exactly this reason. Verify on a
running image:

```sh
systemctl is-enabled x6525-emmc-cacheoff.service x6525-emmc-flush.service   # both: enabled
systemctl status x6525-emmc-cacheoff.service --no-pager
sudo mmc extcsd read /dev/mmcblk0 | grep -iE 'CACHE|Cache'   # CACHE_CTRL should be 0x00
cat /sys/block/mmcblk0/queue/write_cache                     # 'write back': barriers still sent
```

On an image built before this service (or before pkgrel 19), apply the same by hand for the
current and the next boots:

```sh
sudo apk add mmc-utils
sudo mmc extcsd read /dev/mmcblk0 | grep -iE 'CACHE|Cache'   # CACHE_CTRL, CACHE_SIZE
sudo mmc cache flush /dev/mmcblk0
sudo mmc cache disable /dev/mmcblk0
echo "write back" | sudo tee /sys/block/mmcblk0/queue/write_cache   # restore barriers
```

The test is then: repair the filesystem, boot cleanly, power off, boot again. If the fsck stop no
longer appears, the cache was the cause.

The observed split points straight at it: a **reboot keeps the eMMC powered**, so its cache
survives and the next boot is clean; a **power-off cuts the eMMC supply**, so whatever the cache
still held is gone. That is why "power off from the menu, then turn on" corrupted while a hard
reboot did not - and why the fix has to reach the card's cache, not the block queue's flag.

How to read the evidence:

- `mmc0: error`, `I/O error`, or `sdhci` timeouts in `dmesg` - that is a driver/DTS problem. The
  first suspects are the link speed/tuning and the eMMC IO supply; send the lines and the `speed`
  value.
- a clean `dmesg` and a `write_cache` of `write back` - the damage is lost write-back cache on a
  power cut. The write-through rule plus clean reboots is the fix; no kernel change is indicated.

There is no ACM console on this boot by construction, so success looks different: the NCM interface
appears on the host and SSH answers `172.16.42.1` (commands in 1.4). A phone that stays on the
splash for a minute with no new USB interface is a failed boot - use volume-down.

### 1.5 The keyboard appears but does not respond

"The keyboard is on screen" and "the keyboard is running" are different things. Check first:

```sh
pgrep -a buffyboard
```

| `pgrep` | What it is | What to do |
|---|---|---|
| nothing | a dead frame. `buffyboard` drew the keyboard, then `pmos_continue_boot` ran `pkill -f buffyboard` (`postmarketos-initramfs`, `init_functions.sh:1219`); fbcon repaints only the rows something writes, so the keyboard stays on screen with nothing behind it. | the rootfs, not touch - see below |
| a `buffyboard` process | the keyboard is live and touch is not reaching it | restart it with verbose logging (the initramfs instance logs errors only) and read what it does with the input device |

If nothing is listed, the process was killed at switch_root and no service restarted it. An image
built with `ui = console` has no buffyboard service - it is shipped by `postmarketos-ui-buffyboard` -
while `rom.yml` now selects `ui = buffyboard`, which installs it and enables it (the systemd unit via
`postmarketos-base`'s preset; on an OpenRC image the UI's openrc subpackage adds the script to the
default runlevel). `rom.yml` also pins `service_manager = systemd`, because the UI package defaults
to OpenRC and the init system would otherwise change with the UI. Until that image is flashed, start
it by hand over SSH as `user`; it draws on the console and injects keys there, so an SSH session is
enough:

```sh
sudo sh -c 'r=$(cat /sys/class/graphics/fbcon/rotate 2>/dev/null || echo 0); \
  modprobe uinput 2>/dev/null; \
  nohup /usr/bin/buffyboard -r "$r" </dev/null >/tmp/buffyboard.log 2>&1 &'
```

If a process is listed, restart it with verbose logging and read what it does with the input device:

```sh
pkill -f buffyboard
buffyboard -v >/tmp/bb.log 2>&1 &
sleep 2
grep -iE 'input|fb0|libinput|error|can.t' /tmp/bb.log
```

`buffyboard` reads touches through libinput and accepts a device only after udev has tagged it
(`ID_INPUT_TOUCHSCREEN=1`). What the log says:

| Line in `/tmp/bb.log` | Meaning | Next |
|---|---|---|
| `New input device: omnivision_tcm_touch` | buffyboard took the node | if taps still do nothing, events are not arriving: 1.1's `od` test and the interrupt count in 1.3 |
| `... is not an input device` | udev has no `ID_INPUT=1` for it | `udevadm info -q property -n /dev/input/eventN`; send that with `ls -l /dev/input/` |
| `libinput can't use /dev/input/eventN` | libinput refused the node | send the line with `cat /proc/bus/input/devices` |
| `Key ... is ignored`, `Keyboard ... is ignored` | it is a key device, not touch | correct for this board; not the keyboard's problem |
| `/dev/fb0 is not available` | display, not touch | the boot lost the framebuffer early; send `dmesg` |

Tap the screen, then:

```sh
tail -20 /tmp/bb.log
pgrep -a buffyboard
```

`pgrep` should print one line. More than one means an earlier instance is still running; kill them
all (`kill -9 <pid>` if `pkill -f buffyboard` leaves any behind), confirm `pgrep` is empty, and start
one, so the log belongs to a single process.

Read it together with the event read from 1.1:

| event node (`cat \| od`) | `bb.log` | Meaning |
|---|---|---|
| bytes | `New input device: omnivision_tcm_touch` | touch and buffyboard are both fine; the fault is in buffyboard's hit-testing |
| bytes | no line for the device | udev/libinput did not hand it over; the log's warning says why |
| nothing, while the `ovt-tcm` IRQ count rises | - | the handler reads the controller but `tcm_report_touch()` emits nothing; that needs a debug print in the driver |
| nothing, IRQ count static | - | the IRQ is not arriving; see 1.3 |
| - | `pgrep` empty | it exited; the last log lines say why |

If no line mentions the touch device, it never reached udev: use `/proc/bus/input/devices` and the
`dmesg` output from 1.1 to find out whether the driver got to `touch ready`.

### 1.6 Copy-paste: the remaining measurements

These reads decide between the driver and buffyboard. One block, in the debug shell; touch and drag
during the 10-second `cat`.

```sh
pkill -f buffyboard
sleep 1; pgrep -a buffyboard        # should print nothing
buffyboard -v >/tmp/bb.log 2>&1 &
sleep 2

node=$(grep -A4 -i omnivision /proc/bus/input/devices | sed -n 's/.*Handlers=\(event[0-9]*\).*/\1/p')
echo "node=$node"                                       # must be event<number>, not empty
timeout 10 cat "/dev/input/$node" | od -An -tx1 -v      # touch and drag during these 10 s
grep -iE "ovt-tcm|eic" /proc/interrupts                 # count, for comparison

# tap the screen, then:
grep -iE 'New input device|not an input|libinput|fb0|error|can.t' /tmp/bb.log
tail -20 /tmp/bb.log
pgrep -a buffyboard
```

`cat | od` bytes + `New input device: omnivision_tcm_touch` = buffyboard's hit-testing. No bytes
while the `ovt-tcm` count still rises = the driver's report path. An empty `pgrep` at the end =
buffyboard exited; the tail of the log says why.

### 1.7 Touch works; why taps could not reach the keyboard

On 2026-10-20 the event stream was captured and decodes as a complete touch:

```
ABS_MT_TRACKING_ID=296
ABS_MT_POSITION_X=133   ABS_MT_POSITION_Y=2905
ABS_MT_PRESSURE=19 -> 21 -> 23 -> 20 -> 8
BTN_TOUCH=1 ... BTN_TOUCH=0   ABS_MT_TRACKING_ID=-1   SYN_REPORT
```

Each record is 24 bytes: 8-byte seconds, 8-byte microseconds, `u16 type`, `u16 code`, `s32 value`
(little-endian). The driver delivers events; whether it encodes positions correctly is the next
question. buffyboard accepted the device (`New input device: omnivision_tcm_touch`).

The controller's raw range is 5759 x 12895 (8x the 720 x 1612 panel). buffyboard draws its keyboard
in the bottom third: physical y 1075..1611, `tty_height = 1612 - 1612/3 = 1075`
(`buffybox`, `buffyboard/main.c`), so a key tap has raw Y at or above about 8600.

The controlled space-bar tap reported `ABS_MT_POSITION_X=2760` (centre) but `ABS_MT_POSITION_Y=337`.
A bottom tap must produce raw Y ~12600, so the position did not arrive intact.
`tcm_set_report_config()` asked for **12-bit** X and Y fields, and 12 bits hold only 0..4095; raw Y
above 4095 wraps modulo 4096 (`337 + 3*4096 = 12625`, a plausible space-bar position). Y was
therefore always reported in 0..4095, buffyboard mapped it to physical y 0..512 - above its keyboard
at 1075 - and no tap could reach a key.

That is a hypothesis to confirm, not a fact: the firmware image carries the same 12-bit default
(`01 06 04 07 04 08 0c 09 0c ...` at `0x15c2f` and `0x19c53` in `hdl_firmware_01.img`), and the
OmniVision vendor driver for other projects requests 12-bit positions too. What supports the
hypothesis:

- the value after each field code is a **bit width** - both the in-tree Synaptics TCM driver and
  the vendor parser read `bits` and advance the bit offset by it;
- this chip advertises **5759 x 12895**, which needs 13 and 14 bits, and the host chooses the widths
  for exactly that reason;
- the driver now requests 16-bit positions (`4+4+16+16+12+12+16` bits/object; the per-object total
  stays 80 bits, so the payload size is unchanged) and logs at bring-up:
  - `report limits: config N bytes, payload M bytes`
  - `default report config (N bytes): ...` - what the firmware had before the request
  - `report config in use (N bytes): ...` - what the controller reports after it

Those three `dmesg` lines say whether the 16-bit request was accepted.

Before flashing, the current 12-bit kernel can tell wrap from scaling: tap the bottom-left corner of
the display and read the event. Raw Y there is ~12800; a 12-bit wrap reports ~512, while a firmware
that scales into 12 bits reports ~4064.

```sh
node=$(grep -A4 -i omnivision /proc/bus/input/devices | sed -n 's/.*Handlers=\(event[0-9]*\).*/\1/p')
timeout 10 cat "/dev/input/$node" | od -An -tx1 -v   # tap the bottom-left corner during these 10 s
```

After flashing the rebuilt kernel, a space-bar tap should report X ~2760 and Y ~12600 (the true raw
position; the exact value depends on where on the bar it lands). Other results:

- **Y ~270** (`12895 - 12625`) - the panel also reports Y inverted; the driver then needs a Y flip;
- **Y still ~337 and `report config in use` still shows `0c` for X and Y** - the controller ignored
  the wider fields; the next step is to parse the firmware's own layout (the logged default) and
  scale or flip according to what its values show.

## 2. Wi-Fi

Built in (a Unisoc WCN with a mainline `sc23xx` driver); nothing to plug in. It needs
`/lib/firmware/sprd/wcnmodem.bin` and `/lib/firmware/sprd/wifi_board_config.bin` (the package
`firmware-infinix-x6525`; the config is converted from the stock `.ini` by `tools/wifi-ini2bin.py`).

**Verified on hardware 2026-10-21, with no USB link connected**: `wlan0` came up, associated,
`ping google.com` replied, and `apk update` / `apk upgrade` plus a package install (`fastfetch`)
ran. The reconstructed `wifi_board_config.bin` was accepted by the firmware, and the WLAN data path
is real.

The firmware and the modules live in the **rootfs**, not the initramfs: run this in the rootfs, on
the screen or over SSH. `dmesg` needs root. The modules are `sprd_wcn`, `sc23xx_wlan`,
`sc23xx_wlan_sipc` (the built tree also has `btsprdsipc` for Bluetooth).

```sh
ls -l /lib/firmware/sprd/
lsmod | grep -E "sprd_wcn|sc23xx"
sudo dmesg | grep -iE "wcn|sc23xx|sprd_wcn|wlan|rproc|firmware"
ip link
```

Then let NetworkManager use it:

```sh
rfkill list
nmcli device status
nmcli radio wifi on
nmcli device wifi list
nmcli device wifi connect "SSID" password "PASS"
```

| What you see | Meaning | Next |
|---|---|---|
| `wlan0` exists | the driver and firmware loaded; `NO-CARRIER,DORMANT` before association is normal | `nmcli device status` must show it managed, then scan and connect; check `cat /sys/class/net/wlan0/address` is not all zeroes. |
| `nmcli device wifi list` is empty or errors | the scan did not work | send `sudo dmesg \| grep -iE 'sc23xx\|wcn' \| tail -40`. |
| `rfkill` says the radio is blocked | soft/hard block | `sudo rfkill unblock wifi`. |
| no `sprd/wcnmodem.bin` in `ls` | the firmware package did not get installed | send `apk info -L firmware-infinix-x6525`. |
| `firmware too large` / `rproc` errors | the modem image does not fit or the region is wrong | send the `dmesg` lines. |
| remoteproc starts but no `wlan0`, `failed to download config section N` | the WLAN firmware rejected a section | note N. `CRC_ERROR` means the checksums in `wifi_board_config.bin` are not what the firmware expects; any other error with N means the section layout is off. Send the lines. |
| modules not loaded | autoload failed | `modprobe sprd_wcn; modprobe sc23xx_wlan; modprobe sc23xx_wlan_sipc`, then repeat, and send the output. |

The firmware layout of `wifi_board_config.bin` was reconstructed from the stock `sprd_wlan_combo.ko`
and accepted on the hardware on 2026-10-21, so the conversion in `tools/wifi-ini2bin.py` is
validated; keep that script and the test alongside any future firmware rebuild.

#### Associated but no internet

Association alone does not prove the WLAN data path: if the USB link still carries the default
route, pings and `apk` go over USB, not Wi-Fi. Check which route is used and where traffic stops:

```sh
ip -4 addr show wlan0
ip route
nmcli -f GENERAL.STATE,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS dev show wlan0
ping -c2 "$(ip route | awk '/default/{print $3; exit}')"   # the gateway
iw dev wlan0 link
sudo dmesg | grep -iE 'sc23xx|wcn|sipc' | tail -40
```

| What you see | Meaning | Next |
|---|---|---|
| the default route is via `usb0` | traffic is not using Wi-Fi | delete that route (`sudo ip route del default dev usb0`) or give the Wi-Fi connection a lower metric, then retest |
| no IPv4 address/gateway on wlan0 | DHCP from the hotspot did not complete | check the host's hotspot, or set the address manually |
| the gateway pings, `1.1.1.1` does not | the hotspot is not sharing/NATing its upstream | fix the host side (below); Android tethering can need its own NAT rules, the same way USB forwarding did on the A01 Core |
| not even the gateway pings | the WLAN data path itself | send the `dmesg` lines; association without frames is a firmware/SIPC issue |

When the AP is the host phone's hotspot, check the host's sharing before the WLAN path - the
association and DHCP can be perfect while the hotspot forwards nothing:

```sh
# on the hotspot host (A01 Core), as root
ip -br link                    # the AP interface: ap0, wlan1, swlan0, ...
ip route                       # the interface carrying the default (upstream)
cat /proc/sys/net/ipv4/ip_forward
iptables -t nat -L POSTROUTING -n -v
iptables -L FORWARD -n -v | head
```

If `ip_forward` is 0, or there is no MASQUERADE rule for the upstream and no ACCEPT for the AP
interface, add them at the top (`-I`, not `-A`, because netd's DROP rules sit in FORWARD):

```sh
AP=ap0                          # from ip -br link
DEF=$(ip route | awk '/^default/{print $5; exit}')
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -I POSTROUTING 1 -o "$DEF" -j MASQUERADE
iptables -I FORWARD 1 -i "$AP" -o "$DEF" -j ACCEPT
iptables -I FORWARD 2 -i "$DEF" -o "$AP" -m state --state RELATED,ESTABLISHED -j ACCEPT
```

Internet over the USB link (docs in README.md) keeps working as before and is the fallback.

### 2.1 Bluetooth

Status from the sources, not yet from the hardware. An earlier image had `bluetooth.service` enabled
and `btsprdsipc` loaded and still showed no controller; two separate causes were found:

1. **The transport's firmware was missing.** `btsprdsipc_probe()` requests
   `sprd/bt_config_pskey.bin` and `sprd/bt_config_rf.bin` and returns an error if either cannot be
   loaded, so the HCI device is never registered (`drivers/bluetooth/btsprdsipc.c`, the two
   `request_firmware()` calls). `firmware-infinix-x6525` pkgrel 3 now ships both, built by
   `tools/bt-ini2bin.py` from the stock `/odm/firmware/bt_configure_{pskey,rf}.ini`; pkgrel 2 and
   older shipped only the Wi-Fi/remoteproc blobs.
2. **The BD address was never set.** The dtsi's `bluetooth@10` node has
   `local-bd-address = [00 00 00 00 00 00]` with the comment "filled in by bootloader". U-Boot's
   `ft_board_setup()` does fill it in, from its `bdaddr` environment variable. The board environment
   now reads that variable from `/btmac.txt` on the eMMC `prodnv` partition (and `/wifimac.txt` for
   the WLAN MAC), the same files the common UFS environment reads; the loads are guarded, so if the
   files are absent the variables stay unset and the property is written all-zero. The HCI core
   rejects all-zero: it skips `set_bdaddr()` (`net/bluetooth/hci_sync.c`), which is where the driver
   sends the two config blobs and enables the controller. Patch 0013 falls back to a random,
   locally administered address in that case, so the adapter works but its address - and with it the
   pairings - changes on every boot. A stable address therefore depends on `prodnv` actually holding
   those two files; check `bdaddr` in the U-Boot environment (`printenv bdaddr`) and, if it is
   empty, the partition's contents. This path has not been seen on hardware yet.

On an image built from this tree, check:

```sh
sudo dmesg | grep -iE 'btsprd|bluetooth|hci'
systemctl status bluetooth --no-pager
rfkill list
bluetoothctl list
bluetoothctl show
```

- `dmesg` should show `no local-bd-address, using xx:xx:xx:xx:xx:xx` (patch 0013's fallback), then
  the HCI device; `bluetoothctl list` should list `hci0`. `bluetoothctl show` prints the address,
  `powered: no` until `bluetoothctl power on`; then `scan on`.
- No `hci0`: `dmesg | grep btsprdsipc` says whether a firmware request failed (`-2` is ENOENT) or
  the SIPC channel never appeared (compare `dmesg | grep -i wcn` with the Wi-Fi checks above).
  `ls /lib/firmware/sprd/` must list `bt_config_pskey.bin` and `bt_config_rf.bin`.
- `systemctl status` saying `inactive (dead)` means it was never started; `systemctl enable --now
  bluetooth` starts it. If it starts and exits, `journalctl -u bluetooth -b --no-pager | tail -30`.

## 3. GUI

Touch (1) and Wi-Fi (2) are done. The `rom` workflow now builds **Plasma Mobile**
(`ui = plasma-mobile` in rom.yml); the Phosh steps below still apply when `ui` is set back, and the
device package carries both sessions' drop-ins.

### 3.0 What the Plasma Mobile image runs

`postmarketos-ui-plasma-mobile` brings the Plasma Mobile shell and KWin Wayland. The systemd
image starts it through `plasma-mobile.service` (from the `plasma-mobile-systemd` subpackage), a
getty replacement that runs `/usr/bin/startplasmamobile` on tty1 as uid 1000; that script execs
`startplasma-wayland` with `PLASMA_DEFAULT_SHELL=org.kde.plasma.mobileshell`. The base preset
(`90-base.preset`) enables `plasma-mobile.service` and disables `sddm.service`; enabling the unit
creates its `[Install] Alias=display-manager.service` link, and the UI's `-systemd` post-install
covers the case where the unit was already enabled when that ran. `plasmalogin.service` (the
Plasma login manager) is enabled by the same preset when that package is installed.

The display driver choice is the same as for Phosh: only `sprd-drm` has the DCS backlight and the
68x152 mm size that gives the 2x scale, so the device package writes
`/etc/systemd/system/plasma-mobile.service.d/10-x6525-drm.conf` (and the same drop-in for
`plasmalogin.service`) with `KWIN_DRM_DEVICES=/dev/dri/x6525-primary`. The udev rule creates that
symlink only when a sprd-drm card exists; if `sprd_drm` failed to probe, KWin has no device and the
session does not start (simpledrm console and SSH remain).

Check a running Plasma image:

```sh
systemctl status plasma-mobile.service --no-pager
journalctl -b -u plasma-mobile.service --no-pager | tail -40
systemctl show plasma-mobile.service -p Environment | tr ' ' '\n' | grep KWIN_DRM
ls -l /dev/dri/x6525-primary /etc/systemd/system/display-manager.service
cat /sys/class/backlight/td4160/brightness
```

- `plasma-mobile.service` failed and `journalctl` shows `Failed to open DRM device` or no card:
  check `ls /dev/dri` and whether `sprd-drm` probed (`dmesg | grep -i sprd.*drm`).
- The session runs but is not on the panel, or the brightness slider does nothing: the drop-in did
  not apply - `systemctl show ... Environment` must list `KWIN_DRM_DEVICES=/dev/dri/x6525-primary`.
- The shell is up but the screen is mirrored/oversized: KWin's output scale, not the panel size
  reported by `sprd-drm`; `kscreen-doctor -o` shows the mode and scale.

The panel itself has two modes, both from the stock board tree and both at the same 153.6 MHz pixel
clock, so switching between them is only a change of blanking:

- 720x1612 at **60.03 Hz** (timing0: 959x2668 totals) - the board DT's `native-mode`, and the
  driver's preferred mode, matching what the stock system boots;
- 720x1612 at 90.05 Hz (timing1: 933x1828 totals) - listed as an option, not preferred.

A compositor that takes the preferred mode (KWin does) comes up at 60 Hz. Check both modes:

```sh
cat /sys/class/drm/card*-DSI-*/modes     # the second column is the refresh rate
kscreen-doctor -o                        # Plasma: current mode and refresh
# or System Settings -> Display & Monitor -> Refresh Rate
```

90 Hz is selectable in the display settings; the DSI bit clock is unchanged, only the blanking
differs. The mode is 90.05 Hz, not exactly 90. Do not make it the default again until it has been
seen on hardware: with 90 Hz preferred, a rejected modeset leaves the bootloader logo on screen
while the kernel runs.

### 3.1 Test the compositor live, before a build

The image has a working DRM device from `simpledrm` (the framebuffer the bootloader leaves scanning
out), while the real `sprd_drm` stack is still blacklisted. Phosh's compositor (`phoc`) can be tried
on `simpledrm` without reflashing. Install it over Wi-Fi, then start a phoc+phosh session from the
**tty1 login** (the on-screen keyboard is the input; a logind session on the active VT is what gives
the compositor the DRM device):

```sh
sudo apk update            # the image ships the indexes from build time
sudo apk add phoc phosh
# one line, so stopping buffyboard cannot cut the command off:
sudo systemctl stop buffyboard; WLR_RENDERER=pixman phoc -S -E phosh
```

`phoc` and `phosh` are both in Alpine edge `community` for aarch64 (the image's
`/etc/apk/repositories` already lists it). If `apk` says `phosh` is not found, the index is stale:
run `sudo apk update`, then `apk policy phosh` to see which repository it resolves from;
`postmarketos-ui-phosh` in pmaports depends on the same package.

`WLR_RENDERER=pixman` here is only for this bare-simpledrm console test - it asks wlroots to render
in software, so the compositor itself is what is being tested. Panfrost is available and needs no
firmware (section 7); drop the variable to try GLES on simpledrm too. The image's Plasma and Phosh
sessions do not pin the renderer.

| Result | Meaning | Next |
|---|---|---|
| Phosh shell appears | `simpledrm` plus software rendering is enough | go to 3.3 |
| phoc exits with an error | the compositor cannot drive `simpledrm` (or has no seat) | photograph the text and go to 3.2 |

To get the console back afterwards: reboot, or `sudo systemctl start buffyboard`.

### 3.2 If simpledrm fails, enable the real display driver

Drop `initcall_blacklist=sprd_drm_init` from `kernel-cmdline.conf` and rebuild. Risky: if the DPU/DSI
stack fails, the screen goes black. Do it in its own build; SSH over USB or Wi-Fi is the recovery
route.

### 3.3 Switch the UI and build

`rom.yml` now selects `ui = phosh` (keeping the `service_manager = systemd` pin; the Phosh UI also
defaults to systemd and uses greetd with the `greetd-phrog` greeter). Because there is no GPU
firmware, the device package installs the software-renderer drop-in:

```ini
# /etc/systemd/system/greetd.service.d/10-x6525-software.conf
[Service]
Environment=WLR_RENDERER=pixman
```

Build, flash `cache` and `userdata` from the same run, and boot. On a working `simpledrm` the Phosh
shell comes up on greetd; if phoc fails instead, SSH still works and its log says why - then go to
3.2 (enable `sprd_drm`).

What the image gives, and what it will not: greetd-phrog is itself Phosh-based, so the first screen
is a Phosh-style login asking for `user` / `x6525pmos` with the on-screen keyboard. After that:
status bar, notifications, home screen/app grid, quick-settings toggles, app windows and the Phosh
OSK (`phosh-osk-stub`).

The kernel command line now enables `sprd_drm` (`initcall_blacklist=sprd_drm_init` removed), which
is what makes **brightness** work: the panel driver registers the DCS backlight as
`/sys/class/backlight/td4160` (12-bit, default `0xa5a`). The same driver reports 68x152 mm for the
720x1612 mode (~269 DPI), so Phosh's automatic output scale should pick 2 and the tiny first-boot
DPI goes away.

The GUI session is pointed at the real panel rather than the bootloader's simpledrm: a udev rule
creates `/dev/dri/x6525-primary` for the `sprd-drm` card, and the greetd drop-in sets
`WLR_DRM_DEVICES` to it. simpledrm stays as the console fallback. If `sprd_drm` fails to probe, no
symlink appears and phoc cannot start - the console and SSH still work, and `dmesg | grep -iE
'sprd|dsi|dpu|panel'` shows where it stopped; re-adding the blacklist is the fallback. Expect still
**slow rendering** (`pixman`, no GPU firmware), **no camera**, and **no cellular** (no modem
firmware or stack is packaged; the WCN blob is Wi-Fi/Bluetooth only). Internet inside the GUI is
still whatever the connected hotspot provides.

### 3.4 Remove the debug cmdline options

Once the GUI is stable, remove them one at a time, re-testing each: first `cpuidle.off=1` and
`cpufreq.off=1` (find which one stalls the CPUs; see FIRST_BOOT.md), then
`initcall_debug`/`ignore_loglevel`.

### 3.5 Black screen after U-Boot: the panel is not being driven

Symptom: after U-Boot the screen either keeps the logo or goes black; no kernel console and no UI,
but SSH over USB works and the backlight is on. The kernel is running and the sprd DRM stack probes;
the trouble is that no client drives the panel (or the client that does is rejected). The kernel
console stays on `simpledrm`, which the panel is not scanning, so it is invisible.

**The boot flow on this phone, observed 2026-10-24**, is exactly that handoff:

1. U-Boot logs on screen.
2. Black where the kernel logs should be: the kernel is running, but its console is on
   `simpledrm` and the panel is not scanning that memory yet.
3. The pmOS/logo appears: `simpledrm`/fbcon is now on the panel. This proves the panel and the
   bootloader framebuffer path work.
4. Black again after that logo: the session switches to the sprd DRM card (`card1`) and Plasma.
   On the image tested, the panel driver still preferred 90 Hz, so KWin's first modeset is the
   prime suspect; the temporary udev rule fixes the handoff but cannot change the mode.

So "no kernel logs on screen" is not evidence that the kernel failed. SSH, `dmesg`,
`/dev/dri/card1`, the backlight and pmsys all working are the evidence that it did not. After the
pmOS logo, collect:

```sh
ls -l /dev/dri/x6525-primary
ps aux | grep -iE 'kwin|plasmashell|startplasma'
journalctl -b --no-pager _UID=10000 | tail -100
```

- symlink missing: the DEVPATH rule did not match; fix the rule (the new ROM uses
  `DEVPATH=*/display-subsystem/drm/card*`).
- symlink present and the screen still black: the handoff worked and KWin's modeset or Plasma
  itself failed; the `_UID=10000` journal has the reason, and a build with patch 0023 (60 Hz
  preferred) is the next test.

Two things have caused this on this port. Check the first before rebuilding:

1. **The compositor never gets the sprd-drm card.** The image points Plasma (and phoc) at
   `/dev/dri/x6525-primary`, created by
   `/usr/lib/udev/rules.d/90-x6525-drm-primary.rules`. The first rule matched
   `DRIVERS=="sprd-drm"`, and the later attempt matched `DRIVERS=="sprd-drm*"`; **neither can
   match**, because the DRM card device has no `DRIVERS` property at all. Confirmed on the phone
   2026-10-24: `udevadm info -q property -n /dev/dri/card1` prints only `DEVNAME`, and the symlink
   is absent while `/dev/dri/card1` and `/dev/dri/by-path/platform-display-subsystem-card` exist.
   The rule now matches the card's parent path instead:
   `DEVPATH=="*/display-subsystem/drm/card[0-9]*"`. Without the link, KWin/phoc is started with a
   nonexistent device and the panel is never modeset.
2. **The 90 Hz mode is preferred.** The board DT's `native-mode` is timing0 (60 Hz). Patch 0019
   made timing1 (90 Hz) preferred; patch 0023 restores 60 Hz and keeps 90 Hz selectable. On this
   DSI/DPU path a rejected 90 Hz modeset also leaves the bootloader logo in place.

Collect this first (works over SSH):

```sh
ls -l /dev/dri /dev/dri/by-path /dev/dri/x6525-primary 2>&1
ls -l /sys/class/drm
cat /proc/fb
udevadm info -q property -n /dev/dri/card1 | grep -E 'DEVNAME|DRIVERS'
cat /sys/class/backlight/td4160/brightness \
    /sys/class/backlight/td4160/actual_brightness \
    /sys/class/backlight/td4160/bl_power
cat /proc/cmdline
systemctl status plasma-mobile --no-pager
journalctl -u plasma-mobile -b --no-pager | tail -60
sudo dmesg | grep -iE 'sprd-drm|td4160|dsi|dpu|panel|backlight|connector|drm' | tail -100
```

What the result means:

| What you see | Meaning | Next |
|---|---|---|
| `/dev/dri/card1` exists, `/dev/dri/x6525-primary` missing | the udev rule did not match (the card has no `DRIVERS`; match its `DEVPATH` instead) | create the link by hand (below); the port needs the rule fixed |
| no `/dev/dri/card1`, although dmesg says `Initialized sprd ... on minor 1` | the sprd DRM card is not registered (or was removed after init) | send the full `dmesg` from that line and `ls -l /dev/dri`; do not chase the compositor yet |
| symlink exists, `journalctl -u plasma-mobile` shows a DRM/device error | compositor/modeset failure | send the journal; with the 0023 build also try `video=DSI-1:720x1612@60` for one boot |
| `bl_power` is 1 or `brightness` is 0 | backlight off, not necessarily a DRM failure | set `brightness` to `max_brightness` and check the panel init in `dmesg` |

Manual hand-off test, if `card1` exists but the symlink does not:

```sh
sudo ln -sf /dev/dri/card1 /dev/dri/x6525-primary
sudo systemctl restart plasma-mobile
journalctl -u plasma-mobile -b --no-pager | tail -60
```

If the panel lights up, the udev rule is the bug; the port matches the card's
`DEVPATH=*/display-subsystem/drm/card*` now. If the screen is still black, the symlink is not the
remaining problem. The by-path link `/dev/dri/by-path/platform-display-subsystem-card` exists
whether or not the custom one does, so it can stand in for the test (point
`KWIN_DRM_DEVICES`/`WLR_DRM_DEVICES` at it and restart the session).

On an image built before the fix, the DEVPATH rule can also be tried without flashing:

```sh
echo 'ACTION=="add", SUBSYSTEM=="drm", KERNEL=="card[0-9]*", DEVPATH=="*/display-subsystem/drm/card[0-9]*", SYMLINK+="dri/x6525-primary"' |
    sudo tee /etc/udev/rules.d/99-x6525-test.rules
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=drm --action=add
ls -l /dev/dri/x6525-primary
sudo systemctl restart plasma-mobile
```

KWin runs in the user session, not in `plasma-mobile.service`'s cgroup, so the system unit's journal
can look healthy while the compositor has already failed. Look there too:

```sh
systemctl show plasma-mobile -p Environment
ps aux | grep -iE 'kwin|plasmashell|startplasma'
journalctl -b --no-pager | grep -iE 'kwin|plasma|drm|no drm|primary' | tail -80
journalctl -b --no-pager _UID=10000 | tail -80
```

A reboot is the reliable retry after creating the link by hand: KWin lives in the user session and
can survive a restart of the system unit. If KWin exits with a mode/modeset error, the image still
has 90 Hz preferred; use a build with patch 0023 (60 Hz preferred) before chasing the compositor
further. The manual symlink alone cannot fix a rejected 90 Hz mode on the old image.

The 60 Hz test on an older image, for the second cause:

```sh
sh tools/patch-cmdline.sh pmos-boot-fs.img "video=DSI-1:720x1612@60"
fastboot flash cache pmos-boot-fs.img
```

That only affects the kernel's fbdev mode; if the compositor is not using the sprd card at all, it
cannot help.

### 3.6 Deep Diagnostic: If the Screen Still Fails (Black Screen)

If the screen is still black after applying patches 0023 (60 Hz mode default), 0024 (delays and AVDD/AVEE GPIOs), and 0025 (LP command tx and boot handoff), use this systematic triage over SSH:

#### Step 1: Identify the symptom category

| Category | Visible Symptom | Likely Cause |
|---|---|---|
| **A** | Backlight is OFF (screen pitch black, even under a flashlight) | Backlight power/PWM (`bl_power` or GPIO/regulator off) |
| **B** | Backlight is ON, but screen remains completely blank from boot | Panel reset/power rails (AVDD/AVEE) or DSI LP command timeout |
| **C** | Bootloader logo freezes and never changes | Kernel `sprd-drm` driver failed to bind or stalled before mode handoff |
| **D** | Bootloader logo shows, then turns black when Plasma starts | DRM symlink mismatch (`/dev/dri/x6525-primary`), or KWin/Panfrost crash |

#### Step 2: Check Power Rails, Reset, and Clocks

Verify that the panel power GPIOs and DPU clocks are energized:

```sh
# 1. Check panel power & control GPIOs:
sudo cat /sys/kernel/debug/gpio | grep -E 'avdd|avee|reset|te|td4160|panel'
# Expected:
#   avdd-gpios (ap_gpio 54): out hi (1)
#   avee-gpios (ap_gpio 55): out hi (1)
#   reset-gpios (ap_gpio 53): out hi (1)

# 2. Check backlight status:
cat /sys/class/backlight/td4160/brightness
cat /sys/class/backlight/td4160/bl_power
# Force backlight full on for testing:
echo 0 | sudo tee /sys/class/backlight/td4160/bl_power
echo 255 | sudo tee /sys/class/backlight/td4160/brightness

# 3. Check DPU & DPI clocks:
sudo cat /sys/kernel/debug/clk/clk_summary | grep -E 'dispc|dpi|twpll'
# Expected: CLK_DISPC0 running at ~384 MHz, CLK_DISPC0_DPI running at ~153.6 MHz
```

#### Step 3: Inspect MIPI DSI & DRM Driver Errors

Check for communication timeouts or DSI bus errors in dmesg:

```sh
sudo dmesg | grep -iE 'td4160|sprd[-_]drm|dsi|dpu|dispc|panel' | tail -100
```

Look for:
- `panel-td4160-hx ...: attached to dsi host`: panel bound successfully.
- `dsi cmd timeout` or `transfer failed`: command mode / LP transmission failed.
- `wait frame done timeout`: DPI video stream or vertical blanking timing mismatch.

#### Step 4: Bypass the Compositor — Test DRM Hardware Directly with `modetest`

To determine whether the issue is in the kernel DRM driver or in KWin/Wayland user-space, test direct scanout using `modetest`:

```sh
# 1. Stop the graphical environment to release the DRM master:
sudo systemctl stop plasma-mobile   # or greetd if running Phosh

# 2. Inspect connector ID and CRTC ID on the sprd card:
modetest -M sprd -c
modetest -M sprd -p

# 3. Drive an SMPTE test pattern directly to DSI-1 (replace <connector_id> with the ID from above, e.g. 33):
sudo modetest -M sprd -s <connector_id>:720x1612@60
```

- **If the color bars appear on screen**: The kernel DRM driver, DSI bus, DPU, and panel are completely functional! The issue is solely inside KWin, Mesa/Panfrost, or user session permissions.
- **If `modetest` errors out or produces a black screen**: The issue is at the kernel/hardware level (panel init commands, timing parameters, or clock gating).

#### Step 5: Isolate KWin & Panfrost GPU (If `modetest` works)

If `modetest` shows a test pattern but Plasma Mobile displays a black screen:

```sh
# 1. Verify the DRM primary symlink:
ls -l /dev/dri/x6525-primary
# Should point to /dev/dri/card1 (the sprd-drm card)

# 2. Check if Panfrost or KWin crashed:
journalctl -b --no-pager | grep -iE 'kwin|panfrost|mali|drm|failed to open' | tail -80
journalctl -b --no-pager _UID=10000 | tail -80

# 3. Test running KWin with software rendering (bypass Panfrost GPU):
echo "KWIN_COMPOSE=QPainter" | sudo tee -a /etc/environment
sudo systemctl restart plasma-mobile
```

#### Step 6: Visual Recovery Fallback — Boot with `simpledrm`

If you need a working screen immediately for debugging and want to bypass `sprd-drm`:
Add `initcall_blacklist=sprd_drm_init` to the kernel command line:

```sh
# On host:
sh tools/patch-cmdline.sh pmos-boot-fs.img "initcall_blacklist=sprd_drm_init"
fastboot flash cache pmos-boot-fs.img
```

With `sprd_drm` blacklisted, the kernel does not unbind the bootloader's simple framebuffer, and `simpledrm` provides a guaranteed text console and fbcon display at `0x9e000000`.

## 4. Audio

The SC2730 codec, the SPRD platform/machine drivers and the simple amplifier are all modules; the
sound card only exists once they have bound, so "volume at max, no output" starts with whether the
card is there at all. `alsa-utils` may need installing (`sudo apk add alsa-utils`).

```sh
cat /proc/asound/cards
aplay -l
lsmod | grep -iE 'snd_soc|sc2730|sprd'
sudo dmesg | grep -iE 'asoc|snd|sc2730|sprd.*sound|amp'
wpctl status
wpctl get-volume @DEFAULT_AUDIO_SINK@
pactl list short sinks
```

| Result | Meaning | Next |
|---|---|---|
| no card in `/proc/asound/cards` | the machine/codec modules did not bind | send the `dmesg` lines; `sudo modprobe snd-soc-sprd-ums9230` and `sudo modprobe snd-soc-sc2730` to see the error |
| card exists, and `wpctl` shows a sink at max volume | routing or mixer, not volume | `amixer -c 0 scontrols`, `amixer -c 0 contents \| grep -i -A2 -E 'speaker\|hp'`, then `speaker-test -c2 -t sine` |
| card and sink, still silence | amplifier enable or codec output | check the amp GPIO (ap_gpio 113) and the DAPM state in `/sys/kernel/debug/gpio` |

The DTS feeds the amplifier's right input from `HPR_OUT`; an earlier revision had both inputs on
`HPL_OUT` (mono), fixed on 2026-10-24 while chasing this.

## 4.5 USB: OTG host (a keyboard, a stick) and the charger's boost

A USB-C OTG adapter makes the phone the host, and the kernel side mostly works: the Type-C port
manager (sc27xx_pd) detects the adapter, switches the data role to host, and musb-sprd puts the
controller in host mode through the role switch in the board tree. What was missing is the 5 V: the
port's only source is the charger's boost converter, and the port manager's `vbus-supply` had nothing
to enable (`sc27xx_pd_set_vbus()` returns quietly when no regulator is supplied), so a keyboard got
no power and never enumerated. It looked like "host mode with no VBUS", which is also where the
"unknown USB mode" notification comes from.

The port now carries both halves:

- patch 16 makes the bq2415x driver register its `otg-vbus` DT child as a regulator; enabling it
  enters boost mode (charging is disabled while the port sources power) and disabling it restores
  the charger's automatic mode;
- patch 17 adds that child to the charger node and sets `vbus-supply` on `&pmic_typec_pd`.

With a USB-C OTG adapter and a keyboard plugged in:

```sh
dmesg | grep -iE 'musb|usb 1-1|input:|role|bq2415x'
cat /sys/class/typec/port0/data_role        # host while the adapter is attached
cat /sys/class/power_supply/bq2415x-*/mode  # boost while the port is sourcing
lsusb                                        # apk add usbutils
```

If `data_role` says host but nothing enumerates:

- check that `mode` says `boost`; if it does not, the regulator never got enabled (look for
  bq2415x errors in dmesg) or the charger did not accept the boost command;
- the boost converter is the AW32257 at i2c3 0x6a, register-compatible with the bq24158; if its
  boost bit does nothing, the fallback is to write `boost` to the charger's `mode` sysfs entry by
  hand and see whether VBUS appears - that isolates the regulator wiring from the chip;
- a self-powered device (a powered hub) can enumerate even without VBUS, so it is not a good test.

The role switch also allows userspace control, which is useful for isolating the controller from the
port manager:

```sh
cat /sys/class/usb_role/*/role
echo host > /sys/class/usb_role/<name>/role     # data role only; VBUS still needs the regulator
```

## 5. Camera and cellular: the vendor data, and what is still missing

The outputs collected below go into [`unit-data/x6525-stock.txt`](unit-data/x6525-stock.txt) (or a
file next to it) in this repository, not into the chat - the phone cannot upload files here, and the
repository is readable by whoever does the work. `unit-data/README.md` says how to add text (GitHub
web editor works from the phone) and where binaries such as `modem.img` go.

The vendor kernel source is public: `Bocchi-The-Dev/kernel_transsion_ums9230` (Transsion UMS9230,
X6525/X6528/...). Its `ums9230-1h10_go-overlay.dts` is the board this port runs (dtbo entry 18), and
the stock OTA's `/odm/etc/sensor_config.xml` is the camera HAL's slot list. Together they say what
the hardware is; the two things that are per unit rather than per project are noted below.

### 5.1 Camera

Sockets as the running stock kernel has them, read from the live device tree (`/sys/firmware/fdt`;
not kept in this repository - it carries the serial number):

| vendor node | bus | reg | 7-bit addr | phyid | reset | power-down | supplies | clock |
|---|---|---|---|---|---|---|---|---|
| `sensor-sub` (rear, S5K3L6) | i2c1 `200e0000` | 0x5a | 0x2d | 0 | ap_gpio 41 | ap_gpio 40 | vddcamio, vddcama1, vddcamd1 | CLK_SENSOR1 |
| `sensor-main` (front, OV8856) | i2c0 `200d0000` | 0x20 | 0x10 | 2 | ap_gpio 44 | ap_gpio 46 | vddcamio, vddcama0, vddcamd0, vddcammot | CLK_SENSOR0 |
| `sensor-main2` (`fakeserial`, decorative) | i2c1 `200e0000` | 0x20 | 0x10 | 3 | - | - | vddcama1 | CLK_SENSOR2 |

The vendor `reg` values are the 8-bit (write) form of the address; Linux wants the 7-bit one, hence
the second column. There is no `sensor-sub2` client on this unit. The generic vendor overlay
(`ums9230-1h10_go-overlay.dts`) has a different socket layout - it puts `sensor-sub` on i2c0 - so the
live tree, not the overlay, is what the board DTS follows.

`phyid` is the mainline camsys port number: 0 is `CAMSYS_CSI_4LANE`, 2 is `CAMSYS_CSI_M` (two lanes).
The vendor driver's own CSI controller choice (`csi0`/`csi1` in the live tree) is not part of the
mainline binding; the media graph selects a controller at stream time.

There is also a flash controller: `sprd,flash-ocp8137` on i2c5 at 0x63 (and `flash-aw36515` at 0x64
in the live tree), with torch enable on ap_gpio 137 (confirmed from the stock device tree; exposed as the `white:flash` LED), other flash pins unconfirmed, and sync on 121. No mainline
driver yet.

The stock OTA's `/odm/etc/sensor_config.xml` lists what the HAL expects per camera slot:

- slot 0, rear, 90 deg: `hi1336` (tuning hi1336_1835), `s5k3l6` (1836), `hi1336` (1876), `ov13b10` (1893)
- slot 1, front, 270 deg: `gc08a3_4lane` (1829), `ov8856_4lane` (1831)
- slot 2, rear: `fakeserial` (the second rear lens of the SMART 8 is decorative)

**Identified on this unit (2026-10-24).** Opening the stock Camera app once and reading the HAL
properties gave:

- slot 0 (rear): `s5k3l6_1836_13M` - the Samsung S5K3L6, 13 MP. The stock camera stack opens it with
  four MIPI data lanes at 4208x3120 (`camioctl_sensor_if_set: ... mipi 0 10 0 4`);
- slot 1 (front): `ov8856_1831_8M` - the OmniVision OV8856;
- slot 2: `fakeserial` (the second rear lens is decorative).

`persist.vendor.cam.sensor.tuning.list` reads
`id0,s5k3l6_1836;id1,ov8856_1831;id2,fakeserial`, and `/mnt/vendor/productinfo/otpdata` is empty on
this unit.

The port now describes the rear camera and builds a driver for it:

- `patches/upstream/0014-*` adds `drivers/media/i2c/s5k3l6.c`. It is the RFC driver posted by Vincent
  Cloutier (itself a rewrite of Purism's s5k3l6xx carry), adapted to this board: 24 MHz MCLK, four
  lanes, and the three mode register tables taken from the vendor's own userspace sensor library,
  `proprietary/odm/lib64/libsensor_s5k3l6.so` in the public `vendor_X6525` tree, whose mode
  descriptors say `mclk 24, lanes 4` and whose tables carry the PLL, lane and MIPI values used
  below. The stock stack's 4-lane/10-bit setup is visible in the dmesg (`mipi 0 10 0 4`).
- `patches/upstream/0015-*` adds the sensor node and the `&camsys` port to the board DTS: i2c1 at
  7-bit 0x2d, four lanes, `CLK_SENSOR1` at 24 MHz, reset on ap_gpio 41, power-down on ap_gpio 40,
  and the vddcamio/vddcama1/vddcamd1 rails.
- `CONFIG_VIDEO_S5K3L6=m` is in the ROM's kernel config.

The front camera is now described too:

- `patches/upstream/0020-*` adds `camera@10` on `&i2c0` for the front OV8856, plus the two-lane
  `CAMSYS_CSI_M` port. It uses the mainline `ov8856` driver at 19.2 MHz on `CLK_SENSOR0`
  (`TWPLL_96M` parent) and the `vddcamio`/`vddcama0`/`vddcamd0` rails.
- the vendor library (`libsensor_ov8856_front.so`) runs the part at 24 MHz, but the mainline driver
  has register tables only for 19.2 MHz and the SoC clock can supply that, so the node asks for
  19.2 MHz. If the sensor probes but does not stream, the clock/PLL tables are the first suspect.
- the mainline driver has no power-down handling, so a gpio-hog holds `ap_gpio 46` low; the pins are
  not otherwise driven by the driver.
- `CONFIG_VIDEO_OV8856=m` is in the ROM's kernel config.

Mainline support, from the ROM's kernel config:

| sensor | driver | ROM config |
|---|---|---|
| s5k3l6 | `drivers/media/i2c/s5k3l6.c` (added by this port, patch 0014) | `CONFIG_VIDEO_S5K3L6=m` |
| ov8856 | `drivers/media/i2c/ov8856.c` | `CONFIG_VIDEO_OV8856=m` (mainline driver; 19.2 MHz only) |
| ov13b10 | `drivers/media/i2c/ov13b10.c` | `CONFIG_VIDEO_OV13B10=m` (not fitted here) |
| gc08a3 | `drivers/media/i2c/gc08a3.c` | `CONFIG_VIDEO_GC08A3=m` (not fitted here) |
| hi1336 | none | - (not fitted here; the vendor HAL has the tables) |

The SoC side was already done: `&camsys` (CSI/DCAM, `sprd,ums9230-camsys`) and the ISP node exist in
the mainline dtsi, and the mainline reeder board DTS shows the binding pattern. The camera rails
(`vddcamio`, `vddcama0/1`, `vddcamd0/1`, `vddcammot`) are defined in the mainline `sc2730.dtsi`.

What to check on the device, with an image built from patches 0014/0015:

```sh
# did the sensor probe, and what did the CSI/DCAM side create?
dmesg | grep -iE 's5k3l6|camsys|csi|sprd-isp'
media-ctl -p -d /dev/media0
v4l2-ctl --list-devices
v4l2-ctl --list-subdevs
# the sensor's controls: use the test pattern first, it needs neither light
# nor focus and exercises CSI + DCAM on its own
v4l2-ctl -d /dev/v4l-subdev0 --list-ctrls
v4l2-ctl -d /dev/v4l-subdev0 --set-ctrl=test_pattern=2
v4l2-ctl -d /dev/video0 --all
v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=10 --stream-to=/tmp/frame.raw
```

(`v4l2-ctl` comes from `apk add v4l-utils`. The subdev and video numbers come from `media-ctl -p`;
on this SoC the capture node belongs to the DCAM, and the ISP is a separate media entity.)

There is no camera application yet: the mainline sprd stack exposes raw Bayer capture and the ISP
blocks through V4L2, but libcamera has no sprd pipeline handler and there is no 3A. The first
milestone is frames from the sensor, then a userspace pipeline.

The front OV8856 is described by patch 0020. The live tree puts it in `sensor-main`: i2c0 at 7-bit
0x10, `phyid 2` (a two-lane port), reset ap_gpio 44, power-down ap_gpio 46, vddcamio/vddcama0/
vddcamd0/vddcammot, on `CLK_SENSOR0`. The mainline ov8856 driver only knows 19.2 MHz tables, so its
clock is `CLK_SENSOR0` at 19.2 MHz (TWPLL_96M parent, as the reeder does) - the rear sensor is on
`CLK_SENSOR1`, so the two do not conflict. The pin the driver leaves alone (power-down) is held low
by a gpio-hog in the board DTS.

Check both sensors after boot:

```sh
sudo dmesg | grep -iE 's5k3l6|ov8856|i2c|camsys'
media-ctl -p -d /dev/media0
v4l2-ctl --list-devices
# the front sensor's controls (test pattern first, as above)
v4l2-ctl -d /dev/v4l-subdev1 --list-ctrls
```

A probe with no `i2c` error means the address, rails and reset pin are right. No probe at all on
i2c0 usually means the power-down hog or the 19.2 MHz clock: check `dmesg` for
`ov8856 0-0010: failed to get xvclk` / `unsupported clock rate` and `ls /sys/kernel/debug/gpio` for
`ov8856_pwdn`.

### 5.2 Cellular (modem)

The mainline tree already has the modem stack, and the ROM config builds it:
`CONFIG_SPRD_MODEM_REMOTEPROC=m`, `CONFIG_SPRD_PMSYS_REMOTEPROC=m`, `CONFIG_RPMSG=m`,
`CONFIG_RPMSG_WWAN_CTRL=m`, `CONFIG_RPMSG_WWAN_NET=m`, `CONFIG_WWAN=m`.
`drivers/remoteproc/sprd_modem.c` requests six images: `sprd/l_modem.bin`, `sprd/l_deltanv.bin`,
`sprd/l_fixnv.bin`, `sprd/l_runtimenv.bin`, `sprd/l_gdsp.bin`, `sprd/l_ldsp.bin`. The mainline
`ums9230.dtsi` has the `modem@65003400` and `pmsys` nodes (disabled) with the SIPC mailbox, reserved
memory regions and power domains; the reeder board DTS enables `&modem` and `&modem_dai`.

What is missing is the firmware. `&modem` and `&modem_dai` are already enabled in the board DTS, so
the remoteproc probes now and stops at `request_firmware("sprd/l_modem.bin")`; nothing crashes, it
just cannot boot the modem. The images and the unit's NV are not in the OTA - they are the phone's
own partitions, and the NV carries the IMEI. On this eMMC unit (`ls -l /dev/block/by-name`):

| partition | mainline file the driver asks for | what it is |
|---|---|---|
| `l_modem_a` (mmcblk0p20) | `sprd/l_modem.bin` | the modem firmware |
| `l_fixnv1_a` (p13) | `sprd/l_fixnv.bin` | factory NV, carries the IMEI |
| `l_deltanv_a` (p22) | `sprd/l_deltanv.bin` | calibration NV delta |
| `l_runtimenv1` (p17) | `sprd/l_runtimenv.bin` | runtime NV |
| `l_gdsp_a` (p24) | `sprd/l_gdsp.bin` | GDSP image |
| `l_ldsp_a` (p26) | `sprd/l_ldsp.bin` | LDSP image |

`l_fixnv2_a`/`l_runtimenv2` are the other copy of the NV pair, and `l_agdsp_a` is the audio DSP
(not requested by this driver). The `pmsys` node, if it is ever enabled, asks for
`sprd/pm_bootcode.bin` and `sprd/pm_sys.bin`, which come from `pm_sys_a` (p30); the reeder does not
enable `&pmsys` and the modem does not need it to start, so it can wait.

The port does not ship these images. The NV carries the IMEI and the rest are per-unit vendor
images, so a public port must not publish them; instead the device package installs
`x6525-modem-nv.service`, which runs `/usr/bin/x6525-modem-nv` at boot: it copies each file out of
its partition (trimmed to the region size above), then loads `sprd_modem`. The driver is blacklisted
from coldplug so it waits for that. Every phone therefore uses its own images, and nothing is
published.

If the service could not run (a different partition layout, or it failed), the same copy can be done
by hand and the driver reloaded; a reboot is the clean retry because the driver will not have
probed:

```sh
# on pmOS, root
sudo /usr/bin/x6525-modem-nv
ls -l /lib/firmware/sprd/l_*.bin
sudo reboot
```

The images can also be dumped from the stock system (root) if they are needed for inspection; keep
the result **out of the repository**, it carries the IMEI:

```sh
cd /sdcard
for p in l_modem_a l_fixnv1_a l_deltanv_a l_runtimenv1 l_gdsp_a l_ldsp_a; do
    dd if=/dev/block/by-name/$p of=$p.img bs=4M
done
ls -l *.img
```

On the device, with a SIM inserted:

```sh
dmesg | grep -iE 'sprd-modem|remoteproc|sipc|rpmsg|wwan|modem|firmware'
cat /sys/class/remoteproc/remoteproc*/state
ls -l /dev/rpmsg* /dev/wwan* 2>/dev/null
mmcli -L
mmcli -m any
```

Reading the failure:

- `failed to load ... sprd/l_*.bin`, or a missing file, means the extraction did not run: check
  `ls -l /lib/firmware/sprd/l_*.bin` and the service's output (`journalctl -u x6525-modem-nv`).
- `region ... outside memory range` or `firmware too large for region` means the file sizes do not
  match the MECP header - re-trim each file to the region size (the table above) rather than to the
  partition size.
- `state` going to `running` but no `rpmsg` ports and no `wwan` device: the AP released the modem
  core but the firmware did not reach its SIPC loop, or the mailbox/region wiring differs from the
  reeder. That is the interesting failure, and the stock dmesg has the reference behaviour.
- The modem firmware drives the SIM interface itself; nothing in the mainline DT enables the SIM
  rails, so a SIM that stays unpowered would show up as "no SIM" in `mmcli` rather than as an error.
  That is the next thing to look at if the modem does come up.

Userspace: `rpmsg_wwan_ctrl` exposes the AT/control port and `rpmsg_wwan_net` the data port;
ModemManager is already installed by the UI and can drive an AT port. Whether the Unisoc LTE modem
initialises on mainline has never been tried - that is the open question these images now let us
answer.

With the stock system running (root), the modem side is also readable directly:

```sh
dmesg | grep -iE 'modem|sipc|rmb|wwan|sim|imei'
getprop | grep -iE 'modem|radio|imei'
ls -l /dev/block/by-name
find /vendor /odm /mnt/vendor -iname 'l_*.bin' -o -iname '*modem*.bin' 2>/dev/null | head -40
# and the images themselves (copy them off the phone afterwards, or use the
# partition list above and dd from pmOS):
for p in l_modem_a l_fixnv1_a l_deltanv_a l_runtimenv1 l_gdsp_a l_ldsp_a; do
    dd if=/dev/block/by-name/$p of=/sdcard/$p.img bs=4M
done
```

To get both datasets to the host (from the host, over the USB link; the login is in README.md):

```sh
scp user@172.16.42.1:/tmp/partitions.txt /tmp/unit-data.txt /tmp/modem.img.gz .
```

### 5.3 GNSS

The GNSS core belongs to the WCN chip, not to a separate device:

- `drivers/remoteproc/sprd_wcn.c` registers the `gnss` child of the WCN node and copies its firmware
  into `wcn_gnss_region` (0x87600000, 0x1fdc00) when the GNSS remoteproc is booted;
- `drivers/gnss/sprd.c` binds the `gnss_pipe0` SIPC channel and exposes the NMEA stream as
  `/dev/gnss0` (`CONFIG_GNSS_SPRD=m`, built);
- the firmware is `sprd/gnssmodem.bin`, taken from the stock `/odm/firmware/gnssmodem.bin` (the public
  `vendor_X6525` tree); `firmware-infinix-x6525` installs it since pkgrel 5.

Test, with the phone outdoors or near a window:

```sh
dmesg | grep -iE 'gnss|wcn'
ls -l /dev/gnss0
apk add gpsd gpsd-clients
gpsd -n /dev/gnss0
cgps -s        # or gpsmon
```

The first fix is slow (cold start, almanac and ephemeris from scratch); the NMEA stream appearing at
all is the milestone.

The `pm_gnss` -> `gnss_pipe0` channel is modelled under the **pmsys** SIPC link in the mainline
dtsi, so the GNSS device only exists once the pmsys co-processor is running. That is now wired up:

- `sprd/pm_bootcode.bin` is packaged (firmware pkgrel 6). It is the `bootcode` word list from the
  vendor's `proprietary/vendor/etc/modem_sp_info.xml`, not a partition; the driver copies it into
  the 4 KB window at 0x62010000.
- `sprd/pm_sys.bin` is the phone's own `pm_sys_a` partition (1 MB), copied out by
  `x6525-pmsys.service` at boot. It is not published.
- `sprd_pmsys` is blacklisted from coldplug: it requests both files during probe and does not retry,
  so the service loads it after the copy.

Check it after boot:

```sh
systemctl status x6525-pmsys
journalctl -u x6525-pmsys -b
ls -l /lib/firmware/sprd/pm_*.bin
cat /sys/class/remoteproc/remoteproc*/state    # expect "running"
ls /sys/bus/iio/devices                       # the sensor hub creates these
ls -l /dev/gnss0
```

Reading the result:

- `no pm_sys_a partition` or a short/zero file: the partition name or layout differs; the service is
  harmless but pmsys then fails its firmware load.
- `bootcode firmware too large` / `pmsys firmware too large`: the files are not the ones this driver
  expects (it allows 4 KB and 0x2c0000).
- `state` stays `offline` or the driver never appears in `dmesg`: `modprobe sprd_pmsys` and read
  `dmesg | grep -iE 'pmsys|firmware|remoteproc'`. If the bootcode is rejected, the next step is to
  compare it with `modem_sp_info.xml` again; a different `bootcode` attribute means a different
  board revision.
- pmsys runs but no `/dev/gnss0`: the GNSS child is under `&wcn`; check `sprd_wcn` loaded and
  `dmesg | grep -iE 'gnss|wcn'`. The GNSS firmware is `sprd/gnssmodem.bin`, already packaged.

Nothing GNSS-related is installed by default; Plasma's location stack uses geoclue, which can read
from gpsd. `apk add gpsd gpsd-clients` and run `gpsd -n /dev/gnss0`.

### 5.4 Sensors (the sensor hub and the VL53L0X)

The accelerometer, gyroscope, light, magnetometer/compass and proximity sensors are not on the AP's
I2C buses: the stock system reads them through the PM co-processor's sensor hub. The mainline
`sprd_shub` stack exposes them as IIO devices, and its `pm_shub` channel is under the same pmsys
link as GNSS - so **pmsys has to be running first** (5.3). The IIO drivers are modules and autoload
when the channel appears.

```sh
# pmsys first: its state gates everything below
systemctl status x6525-pmsys
cat /sys/class/remoteproc/remoteproc*/state

# what the hub exposed
ls /sys/bus/iio/devices
for d in /sys/bus/iio/devices/iio:device*; do
    echo "$d: $(cat "$d/name" 2>/dev/null)"
done
# a reading; the exact channels depend on the part
cat /sys/bus/iio/devices/iio:device*/in_accel_*_raw 2>/dev/null
cat /sys/bus/iio/devices/iio:device*/in_illuminance_raw 2>/dev/null

# why it did not come up
sudo dmesg | grep -iE 'shub|sensor|pmsys'
lsmod | grep -i shub
```

Reading the result:

- no `iio:device*` at all: pmsys is not running (see 5.3) or its firmware did not announce
  `pm_shub`; the SIPC channel is declared in the dtsi, so a running pmsys with no channel is the
  interesting failure.
- `iio:device*` appear but no `in_*_raw` channels: the hub answered but this unit's sensor parts are
  not the ones the driver expects; send the names and `dmesg`.
- the parts are named in the pmsys image itself (the `pm_sys_a` copy): **SC7A20E** accelerometer,
  **MMC5603** magnetometer, **LS9801** light/proximity. There is no physical gyroscope - the
  firmware exposes a virtual one derived from the others, so a gyro may or may not register. The
  stock system's calibration data lives in `persist` and is not wired up here; readings may be
  uncalibrated until it is.

The time-of-flight proximity sensor is separate and on the AP's I2C: the board DTS has
`proximity@29` on `&i2c4`, `st,vl53l0x`, with XSHUT on ap_gpio 168 and the interrupt on 169. The
stock node used `reg = <0x52>` (the 8-bit form) and a vendor driver, and the stock kernel bound no
driver at 7-bit 0x52, so this node is unverified in both address and pinout.

```sh
apk add i2c-tools
sudo i2cdetect -y 4                 # is anything at 0x29 (or 0x52)?
sudo dmesg | grep -iE 'vl53|i2c4'
ls /sys/bus/iio/devices | grep -i prox
cat /sys/bus/iio/devices/iio:device*/in_proximity_raw 2>/dev/null
```

If nothing answers at 0x29, power the XSHUT line high and re-probe, or try `reg = <0x52>`: the
vendor stack may leave the part at its alternative address. The gpio-hog mechanism used for the
front camera is the model for holding XSHUT.

The fingerprint reader (Goodix on the stock system) has no mainline driver and is not part of this
phase.

## 6. Waydroid (Android container)

The kernel prerequisites are mostly in place: `ANDROID_BINDER_IPC=y` with
`binder,hwbinder,vndbinder`, PSI, memcg, user/net/pid namespaces, seccomp, memfd, the dma-buf system
heap, and FUSE/overlayfs as modules. `ANDROID_BINDERFS=y` was the missing option and is enabled from
2026-10-24 - Waydroid needs it to create its own binder devices.

What the image does not carry yet: the Waydroid userspace (Alpine edge has `waydroid`,
`waydroid-systemd`, `waydroid-nftrules`, and `lxc`) and the Android system image, which
`waydroid init` downloads (needs internet). Graphics: Waydroid renders through its own gralloc,
which on a mainline host means Mesa's gbm/panfrost path through libhybris; that combination is
untested here. If it does not come up, Waydroid falls back to software rendering (SwiftShader) and
still runs, slowly. Both Phosh and Plasma Mobile are Wayland compositors, so Waydroid's session
runs as a window either way.

To try it on an image built after the binderfs change:

```sh
sudo apk add waydroid waydroid-systemd waydroid-nftrules
sudo waydroid init            # downloads system.img/vendor.img; needs network
sudo systemctl enable --now waydroid-container
waydroid session start
```

If it fails: `sudo waydroid log | tail -50`, `ls /dev/binderfs` (Waydroid mounts it),
`sudo dmesg | grep -i binder`, and `systemctl status waydroid-container`.

## 7. GPU (Mali-G57, Panfrost)

The kernel side is ready: the dtsi has an `&gpu` node (our DTS sets `mali-supply = <&vddgpu>` and
`status = "okay"`), and the config builds `CONFIG_DRM_PANFROST=m` with OPP/devfreq support. Alpine's
aarch64 Mesa contains both the panfrost Gallium driver (`mesa-dri-gallium`, already pulled in by
`postmarketos-base-mesa`) and panvk (`mesa-vulkan-panfrost`, now a device dependency).

**No firmware is needed.** The stock vendor module is the Mali **G57 job-manager** driver
(`mali_kbase.ko`, built from `kernel5.4/gpu/natt/mali`, strings `Mali-G57`), and mainline Panfrost
matches Valhall JM as `arm,mali-valhall-jm`. `mali_csffw.bin` belongs to Arm's newer CSF GPUs
(G610 and up), not this one - an earlier revision of this note wrongly expected it.

What is needed is already in the tree: `sprd_drm` probing (so the panel/drm device exists), the
renderer no longer pinned to pixman (phoc/wlroots and KWin both try GLES2 through Panfrost, then
Vulkan, then software), and Mesa's panfrost Gallium driver (aarch64 `mesa-dri-gallium`) plus
`mesa-vulkan-panfrost`.

The GPU now also has a DVFS table, taken from the stock kernel's `operating-points` for this part:
384 MHz at 0.70 V, 512 and 614.4 MHz at 0.75 V, 768 MHz at 0.80 V. Panfrost's devfreq scales through
those; without it the GPU runs at whatever rate the bootloader left and never changes. The stock
table's 850 MHz at 0.80 V is left out for now: the mainline composite GPU clock does not propagate
rate requests to GPLL (it stays at its 750 MHz default), and GPLL also feeds the aux clocks through
`/20`, so 850 MHz needs clock-tree work and hardware testing (see ROADMAP.md).

Checks after booting an image with the display switch:

```sh
sudo dmesg | grep -iE 'panfrost|mali'
ls -l /dev/dri/
# DVFS: the OPP table, the current clock rate and the governor
cat /sys/class/devfreq/*/available_frequencies
cat /sys/class/devfreq/*/cur_freq
cat /sys/class/devfreq/*/governor
journalctl -u plasma-mobile -b --no-pager | grep -iE 'opengl|egl|renderer' | tail -20
journalctl -u greetd -b --no-pager | tail -30     # phosh builds
# draw something and watch the rate move
apk add glmark2 mesa-demos vulkan-tools
glmark2-es2-wayland --benchmark
vulkaninfo --summary
```

### 7.1 GPU thermal throttling

Patch 0021 gives the SoC's `gpu-thermal` zone a 70 C passive trip and a devfreq cooling map to the
GPU (Panfrost registers the cooling device). Before it, the zone only reported. Check the zone and
that the GPU rate moves when the trip is crossed:

```sh
for z in /sys/class/thermal/thermal_zone*; do
    printf '%s %s %s\n' "$z" "$(cat "$z/type")" "$(cat "$z/temp")"
done
cat /sys/class/thermal/thermal_zone*/trip_point_*_type 2>/dev/null
cat /sys/class/thermal/thermal_zone*/trip_point_*_temp 2>/dev/null
# while glmark2 (above) runs in another shell:
watch -n 1 'cat /sys/class/devfreq/*/cur_freq'
```

- The `gpu-thermal` zone must be present, with a passive trip at 70000 and a cooling device. If the
  zone is missing, `ap_thm2` did not probe; send `dmesg | grep -i thm`.
- The GPU rate should drop below its current OPP once the zone crosses 70 C and return after it
  cools. If it never moves, the cooling device did not register; check
  `ls /sys/class/thermal/cooling_device*` and their `type`.

### 7.2 eMMC HS200/HS400 (opt-in test)

The mainline driver marks HS200 broken for every `sprd,sdhci-r11` controller, so the eMMC link comes
up at DDR52 even though the stock kernel runs the same part at HS400. Patch 0022 adds a boot-time
override; it is deliberately **off** by default because the eMMC is the root filesystem.

On the host, add the option to the boot image before flashing (or to an already-extracted image):

```sh
sh tools/patch-cmdline.sh pmos-boot-fs.img sdhci_sprd.enable_hs200=1
```

Then flash `pmos-boot-fs.img` to `cache` and boot. To undo, use `--remove` with the same option.
Keep the microSD image or a debug shell path available: if the link trains badly, the rootfs may not
mount, and the fix is to remove the option from the extlinux `append` line (or reflash the boot
image).

Checks:

```sh
sudo dmesg | grep -iE 'mmc0|sdhci|hs200|hs400|ddr52'
cat /sys/kernel/debug/mmc0/ios 2>/dev/null
# throughput, both at DDR52 and with the override
apk add hdparm
sudo hdparm -t /dev/mmcblk0
dd if=/dev/mmcblk0 of=/dev/null bs=1M count=512 iflag=direct
```

- `dmesg` should show a higher speed mode (`HS200`/`HS400`) and the card should still enumerate with
  its full capacity.
- If it floods `mmc0: error -84` / tuning errors, or the rootfs does not mount, remove the option
  and report the `dmesg` lines. That result is the evidence needed to narrow the quirk.

### 7.3 Suspend

The firmware's PSCI is 0.2, which has no SYSTEM_SUSPEND; the vendor suspends through the PM
co-processor and mainline has no driver for that path. Check what the kernel offers:

```sh
cat /sys/power/state
systemctl suspend
journalctl -b --no-pager | grep -iE 'suspend|psci|s2ram' | tail -20
```

`freeze` alone is expected at most; `mem` should not be offered. A failed `systemctl suspend` here is
a missing driver, not a configuration error. Do not treat it as a regression.

## What to send when asking for help

- Which step and which row of the tables above you are on.
- The exact command output (paste text; a photo is fine for the screen).
- The ROM run number you flashed, and whether `boot_a`, `cache` and `userdata` all came from it.
