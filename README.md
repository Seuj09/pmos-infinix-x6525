# pmos-infinix-x6525

Draft postmarketOS port for the Infinix X6525 (Unisoc UMS9230 / T606, downstream 5.4 kernel).
**Untested.** See `NOTES.md` for what was extracted from the stock boot/vendor_boot/dtbo images,
`linux-infinix-x6525/pmos.config` for the kernel config changes, and `repack.sh` for a manual first-boot test.

The kernel config check runs on GitHub Actions. Open the Actions tab, choose **kernel**, and run the workflow. Mode `config` stops after `olddefconfig`. Mode `image` also builds the Image.

## vendor_boot and the DTB (corrected)

An earlier version of these notes claimed that `deviceinfo_header_version="4"` makes pmbootstrap write a
vendor_boot without the DTB, so boot had to be flashed alone with `repack.sh`. That is wrong:

- boot-deploy (run by mkinitfs) builds **both** boot.img and vendor_boot.img for header v3/v4, and passes
  `--dtb` from `deviceinfo_dtb` to mkbootimg. A generated vendor_boot therefore does carry a DTB — the one
  from the kernel package. `deviceinfo_flash_offset_*` are not used at v4.
- `device-jolla-c2`, which runs on the same SoC, takes the other route: `--header_version 4` is passed only
  through `deviceinfo_bootimg_custom_args`, with `deviceinfo_header_version` left unset, so pmbootstrap never
  generates or flashes a vendor_boot at all — U-Boot, chainloaded from boot.img, supplies the DTB via its
  extlinux config.

`repack.sh` is a manual fallback, not a requirement.
