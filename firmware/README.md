# Touch firmware

`hdl_firmware_01.img` is the HDL image the Omnivision TD4160 touch controller needs. The controller has
no flash, so after every reset the driver has to download it - without this file there is no
touchscreen.

## Where it came from

Copied off the phone itself, out of the stock firmware partition:

```
/vendor/firmware/hdl_firmware_01.img
```

It is the image the module the stock ROM runs actually asks for. The images shipped in the stock
*kernel tree* (`hdl_firmware_0/1.img`, `_b.img`, `_limu.img`) are a different panel project: their
driver selects by a name table of "cw" variants that does not contain `lcd_td4160_hx_*`, and the file
that matters here is the one on the device.

```
158893 bytes
sha512  7a50601faa6229a736111f6458aa30acef8c83c4cb30da5be9520996278106770cd34a16e0a7b169a58b9d78c56bfd04cd830ac79cc0a0dbf6e2531581e7c47a
```

`tools/check-hdl-image.py` verifies it against the rules the driver applies in `tcm_parse_image()`:

```
area 0: BOOT_CONFIG      len=256
area 1: ROMBOOT_APP_CODE len=102400
area 2: APP_CONFIG       len=4096
area 3: DISPLAY          len=8192      <- the panel-specific config
area 4: OPEN_SHORT       len=4096
area 5: not an area, skipped by the driver
valid: the driver will accept this image
```

Note area 3: the stock kernel tree's `hdl_firmware_1.img` has no `DISPLAY` area at all, which is
further confirmation that it is not the right image for this panel.

## The package

`../pmaports/device/testing/firmware-infinix-x6525/APKBUILD` installs this file as
`/lib/firmware/postmarketos/sprd/hdl_firmware_01.img`, which is what the board device tree's
`firmware-name` points at.

`firmware-infinix-x6525-1.tar.gz` next to this file is the upload artifact, built so that rebuilding it
gives the same bytes:

```sh
cd firmware
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime='@0' -cf - hdl_firmware_01.img \
    | gzip -n -9 > firmware-infinix-x6525-1.tar.gz
sha512sum firmware-infinix-x6525-1.tar.gz
```

```
124616 bytes
sha512  a8ae389d7479ad8b3226cfb3a0d153f5306cdbe6a9b85e31584c5e6c7c34232a06562134ac9b3669fb4a0919e3335a830bd2b7b08a87e132c500d22fe70fa176
```

If a different gzip produces different bytes, upload the tarball you built and update the checksum in
the APKBUILD to match.

## Still to do

Publish that tarball somewhere fetchable and put the URL in the APKBUILD's `source=`. A release asset
on a *public* repository works (this port's repository is private, so a release here would not be
fetchable by pmaports CI); `firmware-jolla-c2` in pmaports uses the maintainer's own storage. The file
is `proprietary`, which is why the device package only recommends this package.
