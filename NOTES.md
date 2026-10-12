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
