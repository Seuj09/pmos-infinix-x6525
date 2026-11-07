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

## Step 3, register trace of the whole AVC library (`tools/vsp-reg-trace.py`, disassembly only)
`tools/vsp-reg-trace.py` follows the `ldr x, [ctx]; add x, x, #const; str w, [x, #imm]` pattern that
`vsp-reg-scan.py` cannot see. Run on `libomx_avcdec_hw_sprd.so` it finds 22 functions that touch the
VSP window. Offsets from the window base (0x32000000); `0x73xx` rows in the raw output are fields of
the library's own context, not hardware, and are ignored here.

| Offsets | Where | What it is |
|---------|-------|-----------|
| `0x8008` (W), `0x8010` (R) | `show_bits`, `read_bits`, `long_ue_v`, `long_se_v`, `flush_left_byte` | bitstream module: write a command/bit count to 0x8008, read the result from 0x8010 |
| `0x8024` (W) | `ue_v`, `se_v` | bitstream module: Exp-Golomb read command (result again via the read register) |
| `0x8014` (R) | `uvlc_startcode_follows`, `ProcessPPS` | bitstream status ("more data" style check) |
| `0x802c`, `0x8034`, `0x8038` (R) | `get_nalu_info`, `get_startcode_len` | NAL unit info: start-code length and size, filled by the hardware's start-code search |
| `0x8000`/`0x8004`/`0x8008`, `0x1080`/`0x1084` | `cfg_bsm` | see above |
| `0x1004` (W), `0x1008`/`0x100c`, `0x1020`, `0x1030`, `0x11a0`-`0x11ac` | `VSP_DMA_TRANSFER` | internal DMA that moves a table into the block: 0x11a0 = 0, 0x11a4/0x11a8/0x11ac = the three arguments (source, destination, length), then `0x1020 = 0x140 \| (arg4 << 4)` and `0x1030 = 1` start it; the library polls bit 8 of `0x100c` for completion (bounded at 0x3ffff reads), then writes `0x100`, and 7 to `0x1030 - ...` |
| `0x1010` (W, `0xd0`) | `ARM_VSP_RST`, `H264DecDecode` | reset |
| `0x1018` (W) | `VSP_RELEASE_Dev` | release |
| `0x1028` (W) | `H264DecDecode_NALU`, `H264DecDecode`, debug | interrupt control |
| `0x200`-`0x20c`, `0x10b8` | `VSP_SCALER_CFG` | scaler output setup |
| `0x1088`, `0x108c`, `0x1090`, `0x1120` (R) | `printt_debug_register` | debug-only reads |

What this says about the design (still unconfirmed on the phone):
- The library does **not** write per-macroblock registers. Parsing goes through the hardware bit-reader
  (0x8000 block). The picture and slice decode must therefore be driven by the block's own sequencer from
  **tables uploaded by `VSP_TABLE_TRANSFER`/`VSP_DMA_TRANSFER`** (called once from `H264DecDecode`), not by
  poking registers one at a time. The format of those tables is the thing to recover next.
- So a V4L2 driver needs: the bitstream module sequence (documented above), the table upload, and the
  table contents the stock library builds. The table-building code sits behind `H264DecDecode`
  (call at `0x17ef8`) and is the next function to read.
- Registers 0x1000-0x1090 and 0x8000-0x8038 are the ones a `regs` dump from the phone should show
  structured values in.

## Step 3, the per-picture programming sequence (`H264DecDecode_NALU`, disassembly; correction to the section above)
The previous section guessed that decoding is driven by uploaded tables. That was only partly right:
`VSP_TABLE_TRANSFER` runs once per stream setup (276 bytes copied from the library's read-only data into a
0x3000-byte buffer, table id 0x12, via the DMA at `0x11a0`-`0x11ac`). The picture itself **is** set up
through registers, in this order (`tools/vsp-reg-trace.py` extended to follow the `base + const + index`
forms; function `H264DecDecode_NALU` at 0x17d60, ~0x20a4 bytes):

| Step | Registers | Content |
|------|-----------|---------|
| 1 | `0x1028` = 0 | clear/disable interrupts |
| 2 | `0x1088`, `0x108c`, `0x1090`, `0x10b0` | current picture buffer addresses, each `phys >> 4` (the debug dump reads `0x1088`/`0x108c`/`0x1090` back) |
| 3 | `0x2400+4i`, `0x2500+4i`, `0x2580+4i`, `0x2600+4i`, `0x2680+4i` | per-reference-frame address arrays (`phys >> 4`), one entry per list index `i` (luma, chroma and related planes) |
| 4 | `0x1034`-`0x107c` (19 words), `0x1160`-`0x1170`, `0x1180`-`0x1198` | packed picture/slice parameters built with `bfi`/`ubfiz` from the parsed SPS, PPS and slice header |
| 5 | `0x1038` = `0xffffffff`, `0x1028` = 1, `0x1030` = `0xa` | enable interrupts, then **start** (`0x1030 = 0xa`) |
| 6 | `VSP_POLL_COMPLETE` (ioctl `0x6d07`), `0x1028` = 0, read `0x1120` | wait for the interrupt, clear, read status |

The packing of step 4 is decoded properly in the next sections (the guesses that stood here were
partly wrong and have been replaced).

What is still needed for a V4L2 stateless driver: naming each packed field against the
`v4l2_ctrl_h264_sps/pps/slice_params/decode_params` controls (about 25 words, ~600 instructions to read),
confirming the start/complete sequence on the phone, and the reference-frame addressing (step 3).

## Step 3, the parser structs of the stock AVC library (offsets fixed by the H.264 syntax order)

`H264Dec_ProcessSPS`, `H264Dec_ProcessPPS` and `H264Dec_RestSliceHeader` store each parsed element
at a fixed struct offset. The parse order is the order of the H.264 syntax (`read_bits`/`ue_v`/`se_v`
calls in the disassembly), so the names below follow from the specification, not from guesses. This is
what a V4L2 stateless driver receives as `v4l2_ctrl_h264_sps/pps/slice_params` and has to rebuild.

**SPS struct** (`[ctx + 0x1b8]` is the active SPS; offsets in bytes):

| Off | Element | Off | Element |
|-----|---------|-----|---------|
| 0x01 | profile_idc | 0x1a | frame_mbs_only_flag |
| 0x02-0x07 | constraint_set0..5_flag | 0x1b | mb_adaptive_frame_field_flag |
| 0x09 | level_idc | 0x1c | direct_8x8_inference_flag |
| 0x0a | seq_parameter_set_id | 0x1e (u16) | pic_width_in_mbs_minus1 |
| 0x0b | log2_max_frame_num_minus4 | 0x18 (u16) | pic_height_in_map_units_minus1 |
| 0x0c | pic_order_cnt_type | 0x20 | frame_cropping_flag |
| 0x0d | delta_pic_order_always_zero_flag (poc type 1) | 0x21 | vui_parameters_present_flag |
| 0x0e | max_num_ref_frames | 0x22 | seq_scaling_matrix_present_flag |
| 0x0f | gaps_in_frame_num_value_allowed_flag | 0x23 | chroma_format_idc |
| 0x10 / 0x14 (s32) | offset_for_non_ref_pic / offset_for_top_to_bottom_field | 0x24 / 0x25 | bit_depth_luma/chroma_minus8 |
| 0x164 | num_ref_frames_in_pic_order_cnt_cycle | 0x26 | qpprime_y_zero_transform_bypass_flag |
| 0x570-0x57c | frame_crop left/right/top/bottom offsets | | |

**PPS struct:** 0x01 pic_parameter_set_id, 0x02 seq_parameter_set_id, 0x11 entropy_coding_mode_flag
(CABAC), 0x03 bottom_field_pic_order_in_frame_present_flag, 0x04 num_slice_groups_minus1,
0x06/0x07 num_ref_idx_l0/l1_default_active_minus1, 0x08 weighted_pred_flag, 0x09 weighted_bipred_idc,
0x0a pic_init_qp_minus26, 0x0b pic_init_qs_minus26, 0x0c chroma_qp_index_offset,
0x0d second_chroma_qp_index_offset, 0x0e deblocking_filter_control_present_flag,
0x0f constrained_intra_pred_flag, 0x10 redundant_pic_cnt_present_flag, 0x12 transform_8x8_mode_flag,
0x13 pic_scaling_matrix_present_flag.

**Slice header** (`[ctx + 0x318]`): 0x58 frame_num, 0x5c field_pic_flag, 0x60 bottom_field_flag,
0x6c pic_order_cnt_lsb, 0x70 delta_pic_order_cnt_bottom, 0x74/0x78 delta_pic_order_cnt[0]/[1],
0x0e redundant_pic_cnt, 0x07 direct_spatial_mv_pred_flag, 0x00/0x01 num_ref_idx_l0/l1_active_minus1,
the pred_weight_table around 0x2d0-0x3d8 and 0x354, and `dec_ref_pic_marking` at 0x34.

## Step 3, the parameter block and the first packed words (`H264DecDecode_NALU`, 0x1844c-0x1864c)

**Pointers.** `x8` = active SPS (`[ctx+0x1b8]`), `x28` = active PPS (`[ctx+0x1c0]`, first reused as the
register base `0x61201028` later), `x22` = `[ctx+0x320]` (the first part of the slice header: `+0x3` slice type,
`+0x13c` first_mb_in_slice, `+0x140` pps_id), `x17` = `[ctx+0x318]` (the slice header of the section above),
`x27` = `ctx + 0x16870` (the **parameter block**, filled here, then packed into registers). The register stores
are `0x61201028 + imm`, so `#0x1c` is `0x1044`, `#0x20` is `0x1048`, and so on.

**Slice type** is remapped before use: `w20 = 0` I (and SI/SP), `1` P, `2` B.

**The parameter block** (offset: source). Certain = taken straight from a named SPS/PPS element; inferred = from
the position in the slice header or by use:

| Block | Source | Meaning |
|-------|--------|---------|
| +0x00 | `x22[3]` | slice type (0 I, 1 P, 2 B), certain |
| +0x08 | PPS+0x0f | constrained_intra_pred_flag, certain |
| +0x0c | slice+0x07 | direct_spatial_mv_pred_flag, certain |
| +0x10 | SPS+0x1c | direct_8x8_inference_flag, certain |
| +0x14 | `x22[1]` | slice QP (also passed to `init_contexts` for CABAC), inferred |
| +0x18 / +0x1c | PPS+0x0c / +0x0d | chroma_qp_index_offset / second_chroma_qp_index_offset, certain |
| +0x20 | `x22[0x139]` | disable_deblocking_filter_idc, inferred |
| +0x24 | PPS+0x09 | weighted_bipred_idc, certain |
| +0x2c / +0x34 | slice+0 / slice+1, each limited to the default count of another struct | num_ref_idx_l0 / l1 active, inferred |
| +0x78 / +0x7c | SPS+0x22 / PPS+0x13 | seq / pic_scaling_matrix_present_flag, certain |
| +0x80 | PPS+0x08 | weighted_pred_flag, certain |
| +0x90 / +0x94 | `x22[0x13a]` / `x22[0x13b]` | slice_alpha_c0_offset_div2 / slice_beta_offset_div2, inferred |
| +0xa0 / +0xa4 | PPS+0x12 / PPS+0x11 | transform_8x8_mode_flag / entropy_coding_mode_flag (CABAC), certain |
| +0xa8 | slice+1 | num_ref_idx_l1_active_minus1, inferred |
| +0xac | SPS+1 != 66 | "not Baseline", certain |
| +0xb4 | slice+0x64/+0x68 | picture structure: 0 frame, 1 MBAFF, 2+ field, inferred |
| +0xf8 | `ctx+0x16968` (set in `H264DecDecode`) | slice type of the current picture, inferred |

**Registers decoded so far** (field order and widths are certain, the meaning of a field is certain where its
source is "certain" above):

| Register | Layout |
|----------|--------|
| `0x103c` | bit 31 set; bits 31-25 = slice QP (`x22[1]`, 7 bits); bits 24-16 = `slice+0x18` (9 bits); bits 15-0 = `slice+0x1c` |
| `0x1044` | 31 = profile is not Baseline; 29 = scaling matrix present (SPS or PPS); 28-16 = first_mb_in_slice (13 bits); 15-8 = first MB row, 7-0 = first MB column (after the division by the picture width in MBs, MBAFF-aware) |
| `0x1048` | 15 = explicit weighted prediction in use for this slice (P with weighted_pred, or B with weighted_bipred); 20-19 = disable_deblocking_filter_idc; 18-17 = weighted_bipred_idc; 16 = weighted_pred_flag; 14 = CABAC; 13 = transform_8x8_mode; 12 = direct_8x8_inference; 11 = direct_spatial_mv_pred; 10 = constrained_intra_pred; 9-5 and 4-0 = the two deblocking offsets (5-bit two's complement); 22-21 and 31-23 = two derived reference-structure values |
| `0x104c` | 4-0 = chroma_qp_index_offset, 9-5 = second_chroma_qp_index_offset (both 5-bit signed); 14-10 and 19-15 = (num_ref_idx_l0 - 1) and (num_ref_idx_l1 - 1), 5 bits; 24-20 and 29-25 plus bits 30/31 = the capped reference counts (6 bits each) |
| `0x1050`, `0x1054`, `0x1058` | `slice+0x54`, `slice+0x4c`, `slice+0x50` |
| `0x105c`, `0x1060` | block `+0xc8`, `+0xcc` (picture-structure dependent, one of two stored values) |
| `0x1180` | `(((height+15) & ~15) >> 4) << 20 | ((width+15) & 0xfff0)` from the picture size at `ctx+0x1a2` / `ctx+0x1a0` |

**Still open for the first group:** the sources of `0x1034`, the two fields of `0x103c`, `0x1050`-`0x1060`
(slice-header fields at +0x4c/+0x50/+0x54/+0x18/+0x1c, not yet named) and the meaning of the derived
reference-structure values in `0x1048`. Then the second group (`0x1064`-`0x107c`, `0x1160`-`0x1170`,
`0x1184`-`0x1198`), which is built from the reference lists.

## The bitstream read protocol and the first decoder driver (patch 0067, experimental)
`show_bits`/`read_bits` (disassembly): wait until `0x8020` bit 0 is set, write `n << 24` to `0x8008`,
read the bits from `0x8010`; `read_bits` then writes `(n << 24) | 1` to `0x8008` to consume them.
The driver uses this to skip `header_bit_size` bits of the slice header (in chunks of 32), then starts
the slice. The second register group (reference-index tables, six-bit entries) is still only known
structurally, which is why the driver handles intra slices only.

Patch 0067 adds `vsp-dec.c`, `vsp.h` and `vsp-regs.h` to `sprd-vsp`: a V4L2 stateless decoder
(`/dev/videoN` plus a media device) that is slice-based with Annex B start codes, 8-bit 4:2:0
progressive, NV12 output. Per slice it (1) sets the bitstream module and skips the header,
(2) writes the picture addresses (`0x1088`, `0x108c`, `0x1090`, `0x10b0`), (3) writes the packed words
from the tables above, (4) enables the interrupt, writes `0x1038 = 0xffffffff`, `0x1028 = 1` and
starts with `0x1030 = 0xa`. The interrupt completes the job; a 1 s watchdog resets the block
(`0x1010 = 0xd0`) and fails the buffer.

Everything that is a guess is marked in `vsp-regs.h`: the meaning of `0x1090`/`0x10b0` and the size
of their side-data area (128 and 32 bytes per macroblock, appended to each NV12 buffer), which of the
two deblocking offsets goes where, whether any interrupt means "done" (the status at `0x1120` is
logged with `vsp-dec` dynamic debug), and the start offset of the bitstream module (`0x8000` takes
the byte offset of the NAL header plus `0x400`). Not supported: P/B slices, scaling matrices,
interlaced streams.

First test on the phone (needs an intra-only H.264 clip, e.g. `ffmpeg -i in.mp4 -c:v libx264 -g 1
-profile:v high -x264-params cabac=0 ...`, and a stateless-capable client such as `v4l2-request-test`
or ffmpeg's v4l2-request hwaccel): `dmesg | grep -i vsp`, `ls /dev/video* /dev/media*`,
`v4l2-ctl -d /dev/videoN --all`, then one decode with
`echo 'file drivers/media/platform/sprd/vsp/vsp-dec.c +p' | sudo tee /sys/kernel/debug/dynamic_debug/control`.
Expect failures first (timeouts or IOMMU faults); each one narrows down a guessed register.

### Review pass (decoder)

Fixed after re-reading `vsp-dec.c`: the IRQ handler and the watchdog could both finish
the same job, and a late watchdog could reset the codec under the next job (the running
job is now claimed under `job_lock` by whoever gets there first); the capture buffer's
payload was never set, so userspace saw `bytesused = 0`. Still open: any interrupt counts
as success (error bits unknown), side-data sizes are guesses, P/B slices unsupported.

## JPEG codec: what `jpg.ko` shows (and what is still missing)

The stock dump has only `jpg.ko`; the userspace JPEG library is not in it. `jpg.ko` is as thin as
`vsp.ko`: it enables clocks (`clk_jpg`, `jpg_ckg_eb`, `jpg_domain_eb`, `clk_aon_jpg_emc_eb`,
`clk_vsp_mq_ahb_eb`), does dma-buf to IOVA mapping (own IOMMU, raw int at window +0x3a4/+0x3ac)
and sleeps for the interrupt. What it does reveal about the register window (base `0x36000000`):

| Offset | Use in `jpg_isr` / `jpg_poll_mbio_vlc_done` |
|--------|---------------------------------------------|
| `+0x04` | non-zero while the block is enabled (ISR bails out otherwise) |
| `+0x2c` | interrupt status; bits 0 and 1 and 3 are the sources checked (mask `0xb`) |
| `+0x28` | interrupt clear: write the bit(s) just seen (1, 2, 8); `0xf` clears all after a timeout |
| `+0x20` | read in the timeout message (a status word) |

Two completions are waited for separately, `mbio` and `vlc` (bit 3 = the VLC/bitstream stage, bit 0/1 =
MBIO stage, order not yet established), with a 250 ms timeout each. ioctls use magic `'m'` (0x6d):
`0x6d01` (W, 4 B), `0x6d02` (R, 4 B), `0x6d09` (R, 4 B), `0x6d0b` (RW, 24 B: get iova),
`0x6d0c` (W, 24 B: free iova), as in the VSP.

Nothing in the kernel module programs the decode itself (size, quant and Huffman tables, buffer
addresses, start): all of that is in the userspace library, so a decoder driver cannot be written
honestly yet. `tools/dump-stock-codec.sh` now also copies every library that references
`sprd_jpg`/`/dev/sprd_jpg` (listed in `jpeg-libs.txt`). Next step when a stock dump is available:
disassemble it like the AVC library, then write a V4L2 stateless JPEG decoder (`V4L2_PIX_FMT_JPEG_RAW`)
in `sprd-vsp.ko`, reusing the m2m/request plumbing of `vsp-dec.c`.

## JPEG codec: register map from `libjpeg_hw_sprd.so` (stock dump of 2026-11-03)

`libjpeg_hw_sprd.so` (32-bit Thumb-2, also in `/vendor/lib64`) drives the codec from userspace through
`jpg_write_register(ctx, off, val)` / `jpg_read_register`, which are plain MMIO accesses relative to the
mmap of `/dev/sprd_jpg` (the 0x6230xxxx constants in the code are offsets plus a wrap trick; the real
offset is `value - 0x62300000`). Every write is read back and compared (the library logs a mismatch), so
the registers are plain RW. `tools/re/jpeg-regscan.py` recovers offsets from the disassembly
(`llvm-objdump --triple=thumbv7-linux-gnueabi`). The hardware decodes **baseline only**
("Sorry, we can not support the Progressive image!": progressive goes to a software path), 4:4:4, 4:2:2
(both orientations) and 4:2:0 (`ctx->0x2e` = format), with an optional down-scale and slice output.

Decode set-up, `JpegDec_HwTopRegCfg` (ctx fields are the library's own struct; W = value written):

| Reg | Value |
|-----|-------|
| `0x154` | read, then `0x158` = that value `\| 0xff0000 \| 5` (interrupt enable), then `0x154` = 0 |
| `0x0c` | `width \| ((width + 15) >> 4) << 20` |
| `0x10` | `(height_mcu_delta/2) << 26 \| format << 29 \| (field44 & 0x1fff) << 13 \| (field42 & 0x1fff)` |
| `0x14` | luma stride: width rounded up to 16 (4:4:4 variant: `(width + 7) & 0x1fff8`), then `& 0xfff8` |
| `0x04` | mode word: `0x10140000 + 0x200 [+0x100] + ...`, flags by decode mode (`ctx 0x130..0x138`) |
| `0x1c`, `0x20`, `0x24` | three buffer addresses from ctx `0xc4`, `0xc8`, `0xcc` (IOVA; probably bitstream/Y/UV) |
| `0x28` | cleared, then written from ctx `0x50` |
| `0x30` | `0x960711` (constant) |
| `0x18` | ctx `0x54 - 0x21f` |
| `0x34` | `1` |

Start, `START_HW_DECODE`: `0x38 = ctx[0x14]`, `0x44 = ctx[0x00]`, `0x3c = ctx[0x0c]`, `0x40 = ctx[0x10]`
(four more buffer/length words), then `0x04` is rewritten with the per-format mode word
(`0x10140000 + ((ctx 0x4c & 3) << 10) + 0x200 ...`, `0x2000`/`0x1000` bits from `ctx 0x130..0x138`).
Status: `0x15c` is polled by `JPEGDEC_Poll_DBK_BSM_FOR_SLICE`, `0x168` by `poll_ahb_idle` (AXI master
status), `0x300` read in `JPEGDEC_Slice_Start`. Huffman and quantisation tables go in through
`JPEGFW_configure_vld_reg_jpegDec` / `JPEGFW_configure_validReg` (registers `0x48`, `0x4c`, `0x54`,
`0x94` and an indexed window), built from `g_huffTab`.

Still unknown before a driver can be written: the exact `0x04` mode-word bits, what the four `0x38..0x44`
words are (bitstream address/size vs output planes), the table upload format, and the interrupt bits in
`0x2c` that mean "frame done" versus "error". Next: read `JPEGFW_configure_vld_reg_jpegDec`,
`JPEG_HWDecStart` and `JPEG_HWWaitingEnd` (they go through other PLT stubs, which the scanner does not
follow yet), then implement a `V4L2_PIX_FMT_JPEG_RAW` stateless decoder like `vsp-dec.c`.

### JPEG: table upload and completion (second pass)

- `JPEG_HWWaitingEnd` polls `0x168` with mask `1` until it reads `0` (AXI master idle), up to 0xffffff
  reads; `jpg_read_reg_poll(ctx, off, mask, expected, timeout)` is the library's polling helper.
  The frame-done itself arrives as the interrupt (`0x2c` bits, see the `jpg.ko` table above), which
  the library waits for through the driver's ioctl, then it polls `0x168`.
- `JPEGFW_configure_vld_reg_jpegDec` loads the entropy-decoder tables through the register file at
  `0x48`..`0x14c`. With the library's default tables (`ctx 0xe9` set) it writes `0x48` and `0x4c`
  from `g_huffTab[0..1]`, then 64 words to `0x50`..`0x14c` from `g_huffTab[2..]` (`g_huffTab` is
  `0x288` bytes, and the library also copies the whole block to a second place). With the JPEG's own
  tables it builds them (`JPEGFW_build_hufftab_jpegDec`), writes 16 halfwords of DC/AC code-length
  data to `0x50`.. and `0x90`.., then calls a helper (`0x1176c`) once for luma (tables at `+0x44`)
  and once for chroma (`+0xcc`) that writes the code values to the window starting at `0x110`.
  Quantisation tables go through `JpegEnc_QTableCfg`-style writes (decode side:
  `JPEGFW_AdjustQuantTbl_Dec`).

Plan: a debugfs test in `sprd-vsp.ko` that replays this exact sequence for a small baseline JPEG
(default tables, 4:2:0) and logs `0x2c`, `0x15c`, `0x168` and the output, so the next boot of the phone
turns these guesses into facts before a V4L2 driver is built on them.

### JPEG: the table window, measured on the phone (corrects the table-upload notes above)

The register lab (patch 0070) wrote all-ones to each of the 66 table registers and read back the
writable-bit mask. `0x48` and `0x4c` are full 32-bit. Then four groups of 16 registers:

| Registers | Writable bits, register k = 0..15 |
|-----------|-----------------------------------|
| `0x50..0x8c`, `0x90..0xcc` | the low k+1 bits (a 1-bit register, then 2, ... up to 16) |
| `0xd0..0x10c`, `0x110..0x14c` | two (k+1)-bit fields, at bits 0.. and 8.. (the first register keeps only bit 8) |

So the window is indexed by Huffman code length 1..16, which is a canonical decoder's max-code
table, and the right source is the library's `jpeg_fw_vld_default_max_code` (264 bytes, vaddr 0x8208), not
`jpeg_fw_vld_default_huffTab` (648 bytes at 0x8310) as written in the previous section: that
table wrote 39 of 66 words that read back different (the first run on the phone). The 648-byte table is the
symbol (value) table and goes somewhere else. Reading the max-code table: the first group is the
standard DC luminance table's max codes (`0, 0, 6, e, 1e, 3e, 7e, fe, 1fe, ...`) and the second the DC
chrominance table's (`0, 2, 6, e, ...`); the last two groups are the luminance and chrominance AC ones.
`tools/re/jpeg-lab-tables.py` now emits the max-code table, and every word fits the measured masks.
Still open: where the symbol table (`jpeg_fw_vld_default_huffTab`) is loaded (the DMA/second window
the library copies it to) and what `0x48`/`0x4c` hold.

### JPEG: both table windows verified on the phone, quantisation window found (2026-11-07)

- Max-code window `0x48..0x14c`: the 66 words of `jpeg_fw_vld_default_max_code` read back exactly
  (0 of 66 differ).
- Symbol window `0x2000..0x2284`: the 162 words of `jpeg_fw_vld_default_huffTab` (`configure_huff_tab`
  copies the table to `base + 0x2000 + 4i` and reads each word back) read back exactly (0 of 162 differ).
- Quantisation window (`JPEGFW_AdjustQuantTbl_Dec`, hardware path): for each component table, 32 words
  are written to consecutive registers from `0x1000` (luma `0x1000..0x107c`, chroma `0x1080..0x10fc`;
  the register pointer is not reset between tables). Each word is `q[zigzag[2k]] | q[zigzag[2k+1]] << 16`
  (two 8-bit entries). Measured on the phone: all 64 registers are full 32-bit read/write (all ones read back
  as `0xffffffff`), so the window holds the two-entries-per-word values as is.
- Still open before a decode attempt: the `0x04` mode word, the four start words `0x38..0x44`, the
  interrupt bits in `0x2c`, and which of the three buffer registers (`0x1c`, `0x20`, `0x24`) is the
  bitstream.
- `JpegDec_HwTopRegCfg` mode word (`0x04`), from the disassembly: `0x10140000`, `+0x200` unless the scale
  setting (`ctx 0xe0`) is 2, `+0x100` if that setting is above 0, `+0x80` (or `+0x4080` when `ctx 0x130` is 1),
  `+0x2000` when `ctx 0x134` is 1, `|0x1000` when `ctx 0x138` is 1. With all flags clear that is
  `0x10140280` (the unscaled, plain decode). `START_HW_DECODE` rewrites the word with the per-format value.

## JPEG decode start sequence (static reading of libjpeg_hw_sprd.so)

All register access goes through `jpg_write_register(ctx, reg, val)` / `jpg_read_register`, and every
write is read back and compared (the stock code logs a mismatch).

`START_HW_DECODE(ctx, addr)` (0xc3f4):
- `addr` must be aligned (8 bytes for formats 1-4, 16 for 0/5, 32 otherwise), else it bails out.
- 0x38 = ctx[0x14], 0x44 = ctx[0x00], 0x3c = ctx[0x0c], 0x40 = ctx[0x10] (address-like words).
- 0x04 (mode) = 0x10140281 (+0x4000 if ctx[0x134]==1) + ((ctx[0x4c]&3)<<10 or +0x200) (+0x100 when
  ctx[0xe0]>0) | 0x2000 if ctx[0x130]==1 | 0x1000 if ctx[0x138]==1.

`JpegDec_HwTopRegCfg` (0xcbc4) tail: 0x1c/0x20/0x24 = ctx[0xc4]/[0xc8]/[0xcc], 0x28 cleared then
ctx[0x50], 0x30 = 0x960711, 0x18 = ctx[0x54]-0x21f, 0x34 = 1.

Completion (`JPEGDEC_Poll_DBK_BSM_FOR_SLICE`): poll reg 0x15c; bit0 set = done, bit2 set = error.
Still unknown: what fills ctx[0x00..0x14] (probably Y/U/V and bitstream IOVAs) and the 0x2c bits.

`JPEG_FWInitDecInput(ctx, in)` (0xd270) copies the HAL decode request into ctx: ctx[0x50] = in[4]+in[0x6c]
(bitstream start), ctx[0xc4/0xc8/0xcc] = in[0x10/0x14/0x18] (three output plane addresses, written to
regs 0x1c/0x20/0x24 by HwTopRegCfg), ctx[0x54] = in[0xc], ctx[0x58] = in[0x68] (stream size). ctx[0x2e]
(format 0-6) selects the per-component sampling bytes at ctx[0x28..0x2d]. ctx[0x00..0x14] are not set
here; they come from the driver ioctls (0x6d0e returns a value stored at ctx[0x2ec]).

## First decode probe on the phone (16x16 grey, guessed header)

- `lab_cmd` accepts at most one page per write and aborts a write at the first bad line; a shell
  heredoc/pipe splits long input mid-line, so feed one line per write (`probe.sh` now does).
- `wb` prints the register *read-back*: 0x1c/0x20/0x24/0x28 keep the full 32-bit bus address (they are the
  plane/stream address registers); 0x38/0x3c/0x40/0x44 do NOT (read back 0x0007feff, 0x0000047f,
  0x00ff00ff, 0x000a9000), so they are not addresses.
- Writing the mode word 0x10140481 reads back 0x10140480: bit 0 is a self-clearing start bit.
- After start: no interrupt within 1 s (0x2c = 0), 0x15c = 0x4, 0x168 = 0x1015 (busy bit set), outputs
  untouched. Hypothesis: the codec is waiting for stream data; 0x18 probably carries the stream length
  (stock writes ctx[0x54] - 0x21f).

Probe v2 result: tables now read back correctly (0x48, 0x2000, 0x1000 windows). 0x38/0x3c/0x40 change
after start (0x3c = 0x3b), 0x15c and 0x2c stay 0, outputs untouched, 0x168 = 0x1015 even when idle
(so its bit 0 is not a busy flag). 0x18 does not take 0x72 when written out of order. v3 follows the
stock order exactly: 0x158 = (0x154)|0xff0005 and 0x154 = 0 first, mode 0x10140080, 0x28 cleared then the
stream address, final start word 0x10140281 (earlier guess 0x10140481 was wrong by 0x200).

Probe v3 result: 0x18 takes the stream length once the mode word 0x10140080 is written first; start
bit clears (0x10140281 reads 0x10140280) but 0x2c/0x15c stay 0 and no output is written; 0x158 reads 0
after writing 0xff0005. Static findings used for v4: ctx[0x2e] format code: 0 = 4:2:0 (Y 2x2),
1 = Y 4x1, 2 = 4:4:4, 3 = Y 2x1, 4 = grey, 5 = Y 1x2, 6 = Y 1x4 (table in JPEG_FWInitDecInput);
ctx[0x42]/[0x44] = MCU columns/rows, aligned size = MCUs * MCU size; reg 0x10 = fmt<<29 | rows<<13 | cols;
reg 0x14 = 0 for formats other than 0 and 3.

## First pixels from the hardware JPEG decoder

Probe v4 (16x16 grey, format code 4, reg 0x10 = 0x80004002, reg 0x14 = 0, start word 0x10140281) made the
codec write 128 bytes (the first MCU row, 16 pixels x 8 lines, stride 16) into the Y buffer, with no
interrupt (0x2c = 0) and 0x15c = 0; 0x38 reads 3 afterwards. The pixels are a recognisable gradient
(row 0: 00 00 12 2b 45 5e 76 89 | 7c 6f 84 b9 d6 d6 cf ff, expected 00 10 20 30 .. f0) but wrongly scaled,
because the quantisation window was loaded with one raster value per word. From the library the window
holds two 16-bit values per word in zigzag order (word j = Q[2j] | Q[2j+1] << 16, one table per 0x80 bytes);
probe v5 loads it that way and starts a second time to see whether the next MCU row follows.

Probe v5 result: the second start decoded the next MCU row into the same buffer (one start per MCU row,
output stride = width), and 0x15c read 1 afterwards. The pixels of both runs are not the expected image:
v4 (one low-half value per word) gave a smooth gradient, v5 (stock-style packing in zigzag order) gave
saturated garbage, and neither matches a software decode of the same stream, so the mapping of the 64
quantiser slots (32 words x 2 halves) onto coefficient positions is not what the stock code's read suggested.
`tools/re/jpeg-window-probe.py` / `jpeg-window-fit.py` measure it directly: a hand-made stream of 64 blocks
(one MCU row, 512x8) with one coefficient each and the window filled with slot numbers 1..64.

## Quantiser window mapping, measured (the key to correct pixels)

The window at 0x1000 (one table per 0x80 bytes) is 64 16-bit slots, word w = slot 2w (low) | slot 2w+1 (high).
The coefficient at raster row v, column u is dequantised with slot `rev3(u) * 8 + rev3(v)`, where rev3 is a
3-bit bit reversal (the IDCT runs in bit-reversed order). Found with `tools/re/jpeg-window-probe.py`: 64
blocks with one coefficient each, window filled with the slot numbers; blocks 1-31 gave slot numbers 33,
17, 49, 9, 41, 25, 57 for u = 1..7 along row 0 and 4, 2, 6, 1 for v = 1..4 along column 0, i.e.
slot = 8 * rev3(u) + rev3(v) + 1. The model reproduces both earlier phone outputs exactly (mean error 0.008 and
0.0 over 2 x 128 pixels), including the saturated one. Blocks from number 32 on were not decoded in that
probe: block 32 is the first with a 16-bit Huffman code (symbol 0xF2); real images rarely use those.
Pixels are plain 8-bit (level shift 128 included), written with stride = image width, one start per
MCU row in the probes so far (the probe never needed more than one start for 32 blocks of one row).

## First correct decode

Probe v6 (16x16 grey baseline JPEG from Pillow, tables from the stock library, quantiser window in the
measured bit-reversed slot order, two starts, one per MCU row): three of the four 8x8 blocks came out
identical to the software decode (the only differences are single-LSB rounding in the IDCT), the last block
(the last symbols of the stream) was wrong. 0x15c = 1 after the second start. Hypothesis: the engine reads
ahead of the final symbol, so the stream needs padding after its last byte; the next probe appends EOI and
zero padding and counts them in 0x18.

### Result: the stock-sequence decode is bit-exact on mainline

Probe v7 (stream followed by EOI and 30 zero bytes, 0x18 = padded length) decoded the 16x16 grey JPEG with
all 256 pixels within one LSB of the software decode (7 pixels differ by 1, IDCT rounding). `0x15c` bit 0
(done) is now seen by `poll` right after the first start, and 0x38 counts 4 afterwards. Without the padding
the last block was garbage: the engine reads ahead of the last symbol. Recipe (grey, format code 4):

1. power on, load max-code (0x48..), symbol table (0x2000..), quantiser slots (0x1000.., bit-reversed order);
2. 0x0c = ((W+15)>>4)<<20 + W, 0x10 = fmt<<29 | MCU rows<<13 | MCU columns, 0x14 = 0, 0x04 = 0x10140080,
   0x18 = stream length including padding, 0x1c/0x20/0x24 = plane addresses, 0x28 = stream address, 0x30 = 0x960711,
   0x34 = 1, then 0x04 = 0x10140281 (bit 0 starts);
3. completion: 0x15c bit 0. No interrupt was seen in this mode (0x2c stays 0), so a driver should poll.
Open: colour formats (0 = 4:2:0, 2 = 4:4:4, 3 = 4:2:2) with their chroma planes, images larger than one
buffer, 16-bit Huffman codes (blocks after the first 0xF2 symbol did not decode), restart markers, the
interrupt path, and the meaning of 0x38..0x44.
