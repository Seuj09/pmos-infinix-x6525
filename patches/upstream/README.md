# Kernel patches for the ums9230-mainline tree

Ten patches, cut against `v7.2-rc6-ums9230-0` (the tag the pmaports kernel package pins) and verified
to apply **in this order** to a clean checkout of it, producing byte-identical files to `dts/`,
`drivers/` and `bindings/` — i.e. to what CI compiles.

| # | Patch | Where it belongs |
|---|---|---|
| 1 | `dt-bindings: vendor-prefixes: add Infinix Mobility` | bindings/mainline; patch 2 needs it |
| 2 | `dt-bindings: arm: sprd: add Infinix X6525 board` | bindings/mainline |
| 3 | `arm64: dts: sprd: add device tree for Infinix X6525` | the ums9230 tree |
| 4 | `drm/panel: add driver for the TD4160 HX 720x1612 panel` | the ums9230 tree, later drm-misc |
| 5 | `dt-bindings: input: add OmniVision TCM SPI touchscreen` | bindings/mainline |
| 6 | `Input: add OmniVision TCM SPI touchscreen driver (host download)` | the ums9230 tree, later input |
| 7 | `dt-bindings: power: supply: add extcon-backed USB charger detection` | bindings/mainline |
| 8 | `power: supply: add extcon-backed USB charger detection` | the ums9230 tree, later power-supply |
| 9 | `dt-bindings: gpio: sprd: allow gpio-hog nodes` | bindings/mainline; independent of this board |
| 10 | `dt-bindings: power: supply: sc27xx-fg: allow power-supplies` | bindings/mainline; independent of this board |

Patch 3 adds the touch node together with the rest of the board, and 5 and 6 document and drive it;
the series is only consistent once all ten are applied, which is what the verification below checks.
The build inputs CI applies are separate: `../0001-x6525-build-glue.patch` and
`../0002-x6525-touch-glue.patch`, `../0003-x6525-charger-glue.patch` and `../0004-x6525-gpio-hog-glue.patch` (the same hunks as 1, 2, 4, 5/6's Kconfig and Makefile entries, so a
local build and CI put the same thing in the tree).

```sh
git clone --depth 1 --branch v7.2-rc6-ums9230-0 https://codeberg.org/ums9230-mainline/linux
git -C linux am "$PWD"/patches/upstream/0*.patch
```

`tools/apply-overlay.sh` does the equivalent without `git am`, which is what CI uses.

## Sending them

- **Patches 3 and 4** go to the ums9230 tree first (Codeberg PR, or to the maintainer). That tree's own
  device tree commits carry a `WIP:` prefix; ours do not any more, since the file has no TODOs left and
  every value in it is traced to a named source.
- **Patches 1 and 2**, and ultimately the driver, go to mainline by mail: `devicetree@vger.kernel.org`
  for the bindings and `dri-devel@lists.freedesktop.org` for the panel driver, with the SoC/bindings
  maintainers copied. Keep the binding separate from the driver there, as the series already does.

## Before sending

- The `Signed-off-by:` line is `Seuj09 <jeus110310@gmail.com>`, the identity used in this repo. Amend it
  if you sign off differently (`git rebase -i` with `--signoff`).
- **Codeberg's rules restrict LLM-generated contributions.** Read every line and make the patches yours
  before you submit: the panel sequence is a mechanical conversion of your own device's DT, and the
  device-tree values are extracted from your firmware, but the review and the sign-off are yours.
- None of it has run on hardware. What the file can no longer get wrong, from the live device tree: the
  storage layout, the GPIOs, the charger, the battery profile and the pstore reservation are all read
  off the running system. What still needs the hardware: the panel **reset polarity** (vendor says
  active-high), the **brightness curve** (linear here), the eMMC and SD **phy delay tuning** (the
  vendor's own values, unverified against mainline's driver) and the touch **firmware download**.
  `../../FIRST_BOOT.md` has the list in the order it will matter.

## Not included

Cameras (no mainline driver work started), the WiFi/Bluetooth firmware package (`firmware-infinix-x6525-wcn`),
the USB **source** role (mainline's bq2415x exposes no regulator for the charger's boost, so the port
can only be a device for now), and whatever `charge,chg-pd-gpio` gates — nobody knows yet. The U-Boot
board and the touch driver are separate series: `../upstream-uboot/` and patches 5/6 here.
