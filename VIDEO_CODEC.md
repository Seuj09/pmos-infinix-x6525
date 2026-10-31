# Video codec (VSP) and JPEG: what the stock dump shows

From `tools/dump-stock-codec.sh` run on the stock Android 5.4 system (Infinix X6525).

## The hardware
| Block | MMIO | Interrupt (hwirq) | Stock node |
|-------|------|-------------------|------------|
| Video codec (VSP) | `0x32000000`, 0xc000 | 66 (SPI 34) | `video-codec@32000000`, misc device `/dev/sprd_vsp` |
| JPEG codec | `0x36000000`, 0xc000 | 74 (SPI 42) | `jpg-codec@36000000`, `/dev/sprd_jpg` |

The VSP has its own Unisoc IOMMU (`sprd,iommuvaul6-vsp`) and a DVFS devfreq (`vsp-dvfs`).
Mainline already has the pieces around it: `CLK_VSP`, `CLK_VSP_EB`, `CLK_JPG`,
`UMS9230_POWER_DOMAIN_AP_VSP` and the VSP/JPG resets. It has no DT node and no driver.

## How the stock stack works
- The kernel side (`vsp.ko`, `jpg.ko`, `sprd-vsp-pw-domain.ko`) is thin: power and clock
  gating (`clk_vsp`, `clk_ahb_vsp`, `clk_emc_vsp`, `clk_mm_eb`, `clk_axi_gate_vsp`,
  `clk_ahb_gate_vsp_eb`, `clk_vsp_ahb_mmu_eb`, `clk_vsp_mq_ahb_eb`, parents 76.8/128/153.6/
  192/307.2/384 MHz), a `vsp-dev-eb-syscon` enable register, dma-buf to IOVA mapping, a
  frequency level, and ioctls `VSP_ACQUAIRE/RELEASE/ENABLE/DISABLE/RESET/COMPLETE/HW_INFO/
  GET_FREQ/GET_IOVA/FREE_IOVA/SET_SCENE_MODE`. `VSP_COMPLETE` sleeps until the interrupt.
- The decoding is driven from **userspace**. `libomx_avcdec_hw_sprd.so` (and the hevc, vp9,
  vpx, m4v/h263 decoders, plus avc/hevc encoders) contain `H264Dec_ProcessSPS`,
  `H264Dec_Process_slice`, the DPB and reference-list code and `H264Dec_cfg_bsm`: they parse
  the headers, manage the DPB and write the VSP registers directly through an mmap, then wait
  on the interrupt. Only these libraries know the register map.

## What that means for mainline
That split is the shape of a V4L2 *stateless* decoder: userspace (ffmpeg/GStreamer) already
parses SPS/PPS/slices and hands the driver parsed controls; the driver programs the engine.
So a native driver is realistic, but the register-level programming has to be reverse
engineered from those libraries (no documentation), codec by codec, starting with H.264.

Stages:
1. DT node (`reg`, SPI 34, clocks, power domain, resets, `vsp-dev-eb-syscon`, IOMMU) and a
   bring-up driver that powers the block and reads its version (`GET_HW_MINOR_Version`).
   Needs the stock device tree: re-run `tools/dump-stock-codec.sh`, it now saves `stock.dtb`.
2. A Unisoc IOMMU (VAU) driver or a contiguous-memory fallback for the buffers.
3. Register map for H.264 decode from `libomx_avcdec_hw_sprd.so`, then a stateless V4L2 driver.
4. HEVC and VP9 the same way; JPEG and the encoders last.

An alternative that needs no register work is a compatibility `/dev/sprd_vsp` driver plus the
stock libraries under Waydroid, but that does not give native Linux players hardware decode
and means shipping the vendor blobs.

## Step 1 result: what the stock device tree says (and what is in the kernel now)
From `stock.dtb` (`video-codec@32000000`): registers `0x32000000` (0xc000), SPI 34, clocks
`clk_ahb_gate_vsp_eb` (AP AHB gate 2 = mainline `CLK_VSP_EB`) and `clk_vsp` (AP clock 28 = `CLK_VSP`,
a mux of the TWPLL 256 / 307.2 / 384 MHz outputs, as `vsp_parents` already has), resets
`0x2800` of AP AHB offset 4 (bits 11 and 13 = `RESET_AP_AHB_VSP_GLOBAL_SOFT_RST` and
`RESET_AP_AHB_VSP_SOFT_RST`), power domain `vsp-power-domain` (PMU `0x314`, force shutdown bit 25,
auto shutdown bit 24: the same layout as the MM domain at `0x2e8`). The stock DVFS table runs the
VSP at 256 MHz idle and 384 MHz at work. The VSP's IOMMU (`sprd,iommuvaul6-vsp`, iova `0x20000000`
+ 256 MiB) shares the first 0x80 bytes of the register window; the JPEG codec
(`0x36000000`, SPI 42, resets in MM AHB, power domain MM) has the same shape.

Patches 0038-0040: the AP_VSP power domain, the `video-codec@32000000` node, and `sprd-vsp.ko`
(`CONFIG_VIDEO_SPRD_VSP=m`, not loaded automatically), which powers the block (MM + VSP domains),
enables the clocks, releases the resets and dumps the first 0x200 bytes of registers:

    sudo modprobe sprd-vsp
    sudo cat /sys/kernel/debug/sprd-vsp/regs
    sudo dmesg | grep -i vsp

Send that output: the registers will show whether the block answers (a hang on `cat` or a bus
error means a missing power/clock/reset step) and which words look like version/status registers,
which is where the register-map work starts.

## Steps 2-3: what the stock AVC library shows so far (analysis only, no driver code yet)
`libomx_avcdec_hw_sprd.so` is stripped but exports ~150 symbols (`ARM_VSP_RST`, `VSP_CHECK_DDR_BUS_IDLE`,
`VSP_POLL_COMPLETE`, `H264Dec_cfg_bsm`, `print_debug_register_all`...). Registers reached through
`0x6120xxxx` constants (`tools/vsp-reg-scan.py`; subtract `0x61200000`, add to the `0x32000000` window):

| Offset | Seen in | What it looks like |
|--------|---------|--------------------|
| `0x1010` | `ARM_VSP_RST`, `H264DecDecode` | reset: written `0xd0` |
| `0x101c` | `VSP_CHECK_DDR_BUS_IDLE` | polled with mask `0x101` (AXI master idle) |
| `0x1004`, `0x100c`, `0x1020` | `VSP_DMA_TRANSFER` | DMA (table upload) |
| `0x1028` | `H264DecDecode_NALU` x4, debug dump | interrupt raw/status ("int_raw") |
| `0x1034` | `H264Dec_cfg_bsm` | bitstream-module configuration |
| `0x1400` | `H264Dec_Cfg_ScalingMatix` | scaling-list upload |
| `0x1800` | `init_contexts` | CABAC context init tables |
| `0x8000-0x8024` | `H264Dec_cfg_bsm`, `read_bits`, `ue_v`, `se_v`, `long_ue_v`, start-code search | the **bitstream module**: the library reads SPS/PPS/slice-header bits (`ue_v`, `se_v`) *through the hardware*, not from memory |

The last row matters for the design: header parsing in the stock stack goes through a hardware
bit-reader, so a V4L2 stateless driver (which receives already-parsed controls) must feed the same
bitstream to the module and load the parsed values into the decode registers itself. Only ~22 offsets
come out of the constant scan; the per-macroblock and reference-frame registers are addressed
through base-plus-immediate and need the disassembly read function by function
(`H264Dec_Process_slice`, `H264DecDecode_NALU`, `H264Dec_init_picture`).

The IOMMU side (step 2): `VSP_CHECK_MMU_STATUS` reads eight status registers whose offsets come from a
structure filled by the kernel module, so the MMU (`sprd,iommuvaul6-vsp`, first 0x80 bytes of the window)
layout is in `vsp.ko`, not the library. Until it is mapped, buffers have to be physically contiguous
(CMA) with the MMU left in bypass, which is the fallback the stock library itself has (`cfg_vaor_bypass_en`).

Honest status: steps 2-3 cannot be finished from the dumps alone. They need (a) the `regs` dump from
step 1 to confirm the block answers and to calibrate which offsets are real, then (b) a long,
function-by-function read of the library plus experiments on the phone (feed a known I-frame, compare
the output against ffmpeg). That is weeks of work, not a single patch.

## Step 4 (started ahead of 2-3): the JPEG codec bring-up
Steps 2-3 are paused until the step 1 dump exists. Step 4's other parts (HEVC, VP9, the encoders)
all need the register map of step 3, so they cannot start. The JPEG codec can: it is a separate
block with its own small register window, and the stock device tree describes it completely.
Patches 0041-0042 make `sprd-vsp.ko` bind `sprd,ums9230-jpg` as well (clocks and resets come from
the DT now) and add `jpeg-codec@36000000`: SPI 42, clocks `CLK_MM_CKG_EB`, `CLK_MM_JPG_EB`, `CLK_JPG`
(parent: 256 MHz TWPLL), reset `RESET_MM_AHB_JPG_SOFT_RST_MASK` (the stock mask `0x80000` = bit 19),
MM power domain. `/sys/kernel/debug/sprd-jpg/regs` dumps it; see `VSP_TESTS.md`, test 4b.
Baseline JPEG decode is far simpler than H.264 (no reference frames, no CABAC), so it is the
best first block to get real work out of. The stock `libjpeg`-side library is next to read.

## First register dump (step 1 on the phone, kernel pkgrel 34)
The module loaded, nothing hung, and the first 0x200 bytes read back as real values: the power
domain, clocks and resets are right (`ap_vsp` was off before, `vsp-clk` ran at 256 MHz). But the
values are the **IOMMU's** registers, not the codec's: the stock tree puts `sprd,iommuvaul6-vsp`
at `0x32000000` with size 0x80, and the dump shows exactly that shape:

    0000: 00000100 00000008 ...      (version/ctrl-looking words)
    0020: 000fffff 00000000 0000ffff 00000000   (a 0xfffff limit, then 0xffff ranges)
    0030: 0000ffff 00000000 0000ffff 00000000
    0040: 0000ffff ...
    0080: 01000000

Everything from 0x50 to 0x1ff reads zero, so the codec's registers are elsewhere: the vendor
library uses 0x1000-0x1060, 0x1200, 0x2080, 0x2400, 0x2480 and the bitstream module at 0x8000.
Patch 0043 dumps those ranges (and 0x400 bytes of the JPEG window). If those answer, the next
step is reading what the stock code writes to them before a decode.

## Step 2: the VSP's IOMMU (patches 0045-0047)
The first dump showed that the first 0x80 bytes of the VSP window are an IOMMU whose layout matches the
mainline Unisoc VAU driver (`sprd-iommu`, compatible `sprd,iommu-v1`): word 0 = `0x100` (version byte
`1` = VAU), `0x20` = `0xfffff` (the VPN range register's reset value). So no new IOMMU driver is needed:
- 0045 teaches `sprd-iommu` two things the VSP needs: optional (shared) resets released before the
  version is read (a block in reset reads version 0, which the driver would take for the *other* layout),
  and a runtime-PM reference so the `ap_vsp` domain stays on while the IOMMU is bound.
- 0046 adds `iommu@32000000` (256 MiB window at `0x20000000`, from the stock tree; clock `CLK_VSP_EB`,
  the two VSP resets, domain `AP_VSP`) and `iommus = <&iommu_vsp>` on the codec.
- 0047 makes `sprd-vsp` map its window without claiming it (the IOMMU owns the first 0x80 bytes, as in
  the stock tree), share the resets, and adds `iommu_test` (allocate 256 KiB through the IOMMU, check the
  bus address and the readback). See `VSP_TESTS.md`, test 4c, including the boot kill-switch.
This gives scatter-gather buffers for the decoder; whether the codec's bus master is translated is only
testable once the codec runs. The fallback without it is CMA (32 MiB, `CONFIG_CMA_SIZE_MBYTES=32`) with
the IOMMU in bypass, as the stock library's `cfg_vaor_bypass_en` does.

## Step 3 (partial): how a decode job completes
Checked in the stock `libomx_avcdec_hw_sprd.so` (disassembly, not yet confirmed on hardware):

- **The library does not poll a register to finish a job.** `VSP_POLL_COMPLETE` calls `ioctl(fd, 0x6d07,
  &status)` and sleeps in the kernel until the interrupt fires; it retries up to 9 times while bit 30 of
  the status is set, then branches on the status value (2 or 4 = done, anything else = error path that
  logs and reads the interrupt status). So the kernel module owns the wait: a V4L2 driver can do the same
  with a completion on the VSP interrupt (SPI 34).
- **Bus-idle and similar checks use a generic poll helper** (`vsp_read_reg_poll`): read the register at
  an offset, mask it, wait for an expected value, bounded count. Offsets passed through it include
  `0x101c` (DDR bus idle, mask `0x101`). Ioctl `0x6d09` is the timeout path that sets a flag in the
  context (`|= 8`).
- **Ioctl numbers seen from userspace** (magic `'m'`): `0x6d00`-`0x6d0f`, plus `0x40046d01` (a 4-byte
  write). `ACQUIRE` uses `0x6d05`, `0x40046d01`, `0x6d03`, then the bus-idle check, then `0x6d08`. The names
  (`VSP_ACQUAIRE`, `RELEASE`, `ENABLE`, `DISABLE`, `RESET`, `COMPLETE`, `HW_INFO`, `GET_FREQ`, `GET_IOVA`,
  `FREE_IOVA`, `SET_SCENE_MODE`) are in `vsp.ko`, but **the number-to-name mapping is not confirmed**: the
  dispatcher uses a jump table, and matching it needs a longer pass over `vsp_ioctl` (`/tmp/vsp_ioctl.dis`
  is produced by `llvm-objdump -d vsp.ko`).

**Still missing for a decoder:** the per-macroblock and reference-frame register writes, and what
`H264Dec_cfg_bsm` loads into the bitstream module at `0x8000`. Those need the same function-by-function
pass, and then experiments on the phone. Step 3 is not done.

**What the next phone dump should answer** (after `VSP_TESTS.md` test 4, with patch 0043):
- Does `0x1028` (interrupt status) read as plausible values, and does it change after `modprobe`?
- Does `0x101c` read as a bus-idle value (`mask 0x101` bits clear when idle)?
- Does `0x8000` read as a stable value (the bitstream module's configuration)?
Structured values there would confirm the offsets. Constant or `ffffffff` values would mean the core is
still gated or in reset, and step 1's clock/reset sequence needs another look.

## Step 3, first register facts: `H264Dec_cfg_bsm` (disassembly, not yet confirmed on hardware)
Offsets are from the VSP window base (0x32000000); the library's `0x6120xxxx` constants are the same offsets.
`llvm-objdump -d --disassemble-symbols=H264Dec_cfg_bsm libomx_avcdec_hw_sprd.so`:

| Offset | Access | Meaning (inferred) |
|--------|--------|--------------------|
| `0x8018` | poll, bit 27 must be 0 (bounded at 0x3ffff tries) | bitstream module busy; waited for before reprogramming |
| `0x1080`, `0x1084` | write `stream_buf_phys >> 4` (both) | bitstream buffer address |
| `0x8008` | write `6` | bitstream module mode/config |
| `0x8004` | write `length \| 0x80000000` (or `0xc0000000` when the mode argument is non-zero) | buffer length plus a mode flag |
| `0x8000` | write `(offset + 0x400) \| 0x80000000` | start trigger |
| `0x801c` | poll, bit 2 must be 1 | bitstream module ready (only when the mode argument is non-zero) |

The address written is `>> 4`, so buffers must be 16-byte aligned. Next: `H264Dec_Process_slice`,
`H264DecDecode_NALU`, `H264Dec_init_picture` for the per-picture and reference-frame registers.
