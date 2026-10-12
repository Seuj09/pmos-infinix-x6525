# pmos-infinix-x6525

Draft postmarketOS port for the Infinix X6525 (Unisoc UMS9230 / T606, downstream 5.4 kernel).
**Untested.** See `NOTES.md` for what was extracted from the stock boot/vendor_boot/dtbo images,
`linux-infinix-x6525/pmos.config` for the kernel config changes, and `repack.sh` for a manual first-boot test.

The kernel config check runs on GitHub Actions. Open the Actions tab, choose **kernel**, and run the workflow. Mode `config` stops after `olddefconfig`. Mode `image` also builds the Image.
