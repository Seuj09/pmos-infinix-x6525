# Facts extracted from your files
- boot.img: header v4, page 4096, os A13 patch 2025-10, kernel = 5.4.302-Helix arm64 Image (EFI stub), no AVB footer
- vendor_boot.img: header v4, kernel_addr 0x8000, ramdisk_addr 0x5400000, tags 0x100, dtb_addr 0x1f00000,
  cmdline "console=ttyS1,115200n8 androidboot.selinux=permissive enforcing=0"
  ramdisk table: [0] platform 2.2 MB (only first_stage_ramdisk, no .ko), [1] "recovery" 45 MB
  DTB section: container with 1 FDT, model "Spreadtrum UMS9230 1H10 SoC", compatible sprd,ums9230
- dtb_a: all zeros, so the DTB comes from vendor_boot
- dtbo.img: 21 entries, bootloader picks idx 18 (androidboot.dtbo_idx=18): "UMS9230-1H10-GO Board",
  with panel variants lcd_td4160_hx / lcd_td4160_txd / lcd_ft8057s_dpt and touch (focaltech/omnivision)
- Panel and touch are chosen by the bootloader from the cmdline (lcd_name=lcd_td4160_hx_mipi_hdp_x6525, tp_vendor_id=0x130)

# First boot (SSH over USB)
1. On GitHub: Actions → kernel → Run workflow. Mode `config` is the olddefconfig gate and does not need clang. Mode `image` also builds Image and modules with kernel.org LLVM 14 and `gcc-aarch64-linux-gnu`. The kernel ref defaults to `bpf-a17-selinux-test`.
   Locally: `PMOS_KERNEL_MODE=config ./build-kernel.sh <kernel tree>`, or `./build-kernel.sh <kernel tree> <clang dir>` for the full build. No `pmos` branch is required.
2. Build a **gzip** postmarketOS initramfs (kernel 5.4 cannot unpack zstd)
3. Back up boot_a, check `fastboot getvar current-slot`, then `./repack.sh Image initramfs.gz` and `fastboot flash boot_a boot-pmos.img`
4. Flash the rootfs to **`super`**, not `userdata` (sparse) — that is the partition the UMS9230 port uses (`deviceinfo_flash_fastboot_partition_rootfs="super"`). This erases Android data. The initramfs looks for the `pmOS_root` label
5. On the host a `rndis` USB network interface should appear. Add `pmos.debug-shell` to the cmdline if it does not
If the phone reboots into Android first-stage init, the bootloader ignored the boot ramdisk and the vendor ramdisk must be replaced.

# Build notes
- No `pmos` branch is needed: build-kernel.sh merges pmos.config onto the stock Helix config in an out directory. The workflow and the local script share that gate: every `=y` and every turned-off symbol in `pmos.config` must survive `olddefconfig`.
- MODULE_SIG and MODULE_SIG_ALL stay on (only MODULE_SIG_FORCE is turned off), so modules are still signed; built-in drivers need no key to boot.
- The release string is normally `5.4.302-Helix+` (the `+` disappears on an annotated-tag checkout), which is what the kernel APKBUILD expects.
- Correction to an earlier note here: `deviceinfo_header_version="4"` does **not** drop the DTB. boot-deploy builds a vendor_boot.img for v3/v4 and embeds the DTB from `deviceinfo_dtb` (the kernel package's dtbs) with mkbootimg; `deviceinfo_flash_offset_*` are ignored at v4. Flashing boot alone with `repack.sh` is a fallback, not a requirement. See README.
