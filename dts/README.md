# Device tree for the Infinix X6525

`ums9230-infinix-x6525.dts` is the board device tree for this phone. It belongs in the mainline tree at
`arch/arm64/boot/dts/sprd/` (the `ums9230` branch of
[codeberg.org/ums9230-mainline/linux](https://codeberg.org/ums9230-mainline/linux)), next to
`ums9230-reeder-s19mps.dts` — its structural template. CI builds the DTB on every push and
`../patches/upstream/0003-*.patch` is the submission copy of this file; nothing in it has run on the
hardware yet.

## Where each value came from

The authority for the board values is **the running stock system's own expanded device tree**
(`/proc/device-tree` on the stock ROM, read with `../tools/dtdir-dump.py`): that is what the vendor
kernel was actually handed, so it beats both the dtbo and the stock source tree. `../NOTES.md` records
the path each value came from.

| Section | Source | Status |
|---|---|---|
| `compatible`, `aliases`, `chosen` | device's own stock images (see `../NOTES.md`) | traced |
| `reserved-memory` | reeder DTS; framebuffer base from `lcd_base`, `ramoops` and `tkv-mem` from the live tree | traced |
| backlight | none: the panel takes DCS brightness, the board has no PWM backlight | traced (12-bit, max 0xfff) |
| `gpio-keys` | live tree: vol-down `ap_gpio 124`, vol-up `pmic_eic 4`, power `pmic_eic 1` | traced |
| storage | live tree: eMMC on `sdio3` (`sprdboot.flash=emmc`), microSD on `sdio0` | traced, with the device's own timing values |
| USB (`hsphy`, `usb`) | reeder (MUSB is the same controller); role switch settled from the live tree (`&pmic_typec_pd`) | traced |
| charger | live tree: Awinic AW32257 (reads back as a bq24158) on `i2c3` at `0x6a` | traced; `charge,chg-pd-gpio` (ap_gpio 115) hogged low |
| panel | device cmdline: `lcd_td4160_hx_mipi_hdp_x6525` | confirmed TD4160 HX, 720x1612; driver in this repo |
| touchscreen | device: bound driver `omnivision_tcm_spi` on `spi3.0` | confirmed Omnivision TCM; driver in this repo |
| `cpufreq`, `gpu`, `modem`, codec, uart | reeder (same SoC) | traced |

## Still to be filled in

1. **Nothing is marked unknown any more.** The five TODOs — the USB role-switch provider, the
   `otg-vbus` supply, the panel's vendor prefix, the sound card, and the `ramoops` values — were
   each settled from the live tree and are now written up as the decision and its reason, in
   place. The header still defines the `[T]` marker, which every traced value carries.
2. **Hardware confirmation** — the panel reset polarity, the DCS brightness curve and the eMMC timing
   values are the vendor's own until this kernel runs on the phone. `../FIRST_BOOT.md` lists what to
   watch, in the order it will matter.
3. **Around the DTS** — pmaports CI wants the wiki device page (`../wiki/`) listed before the MR.

## Upstreaming checklist

- `Documentation/devicetree/bindings/vendor-prefixes.yaml`: add `^infinix,.*` — **not present today**.
- `Documentation/devicetree/bindings/arm/sprd/sprd.yaml`: the `ums9230` enum currently lists only
  `reeder,s19mps`; add `infinix,x6525`.
- Note that Codeberg's rules restrict LLM-generated contributions — write and sign off the patches
  you send upstream yourself.
