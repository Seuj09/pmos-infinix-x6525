# Kernel patches for the ums9230-mainline tree

Four patches, cut against `v7.2-rc6-ums9230-0` (the tag the pmaports kernel package pins) and verified
to apply **in this order** to a clean checkout of it, producing byte-identical files to `dts/`,
`drivers/` and `bindings/` — i.e. to what CI compiles.

| # | Patch | Where it belongs |
|---|---|---|
| 1 | `dt-bindings: vendor-prefixes: add Infinix Mobility` | bindings/mainline; patch 2 needs it |
| 2 | `dt-bindings: arm: sprd: add Infinix X6525 board` | bindings/mainline |
| 3 | `WIP: arm64: dts: sprd: add device tree for Infinix X6525` | the ums9230 tree |
| 4 | `WIP: drm/panel: add driver for the TD4160 HX 720x1612 panel` | the ums9230 tree, later drm-misc |

```sh
git clone --depth 1 --branch v7.2-rc6-ums9230-0 https://codeberg.org/ums9230-mainline/linux
git -C linux am "$PWD"/patches/upstream/0*.patch
```

`tools/apply-overlay.sh` does the equivalent without `git am`, which is what CI uses.

## Sending them

- **Patches 3 and 4** go to the ums9230 tree first (Codeberg PR, or to the maintainer). Its own device
  trees carry the `WIP:` prefix, so these match the tree's conventions.
- **Patches 1 and 2**, and ultimately the driver, go to mainline by mail: `devicetree@vger.kernel.org`
  for the bindings and `dri-devel@lists.freedesktop.org` for the panel driver, with the SoC/bindings
  maintainers copied. For mainline, drop the `WIP:` prefix and keep the binding separate from the driver.

## Before sending

- The `Signed-off-by:` line is `Seuj09 <jeus110310@gmail.com>`, the identity used in this repo. Amend it
  if you sign off differently (`git rebase -i` with `--signoff`).
- **Codeberg's rules restrict LLM-generated contributions.** Read every line and make the patches yours
  before you submit: the panel sequence is a mechanical conversion of your own device's DT, and the
  device-tree values are extracted from your firmware, but the review and the sign-off are yours.
- None of it has run on hardware. In order, the things to check: the panel **reset polarity** (vendor DT
  says active-high, the sibling driver assumes active-low), the **brightness curve** (linear here), the
  SD card-detect controller (`eic_sync` vs `eic_async`), and the eMMC **bus width**.

## Not included

Touch (Omnivision TCM over SPI), charging (Awinic AW32257 behind Transsion's `tran_charger`), cameras,
and the U-Boot board for the X6525. Each is a separate job; none block a first boot.
