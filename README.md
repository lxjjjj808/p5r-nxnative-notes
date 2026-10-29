# Persona 5 Royal on iPad Air 5: Windows build and rendering bring-up

Recorded on 2026-10-28. This report documents a local nxnative fork based on
[xbunax/nxnative](https://github.com/xbunax/nxnative), whose upstream is
[seedds/nxnative](https://github.com/seedds/nxnative).

## Latest build shared by the owner

- File: `P5R-M1-fix2.ipa` (final M1 build).
- [Baidu Netdisk download](https://pan.baidu.com/s/1Nzd4eHpYvr2CkyEozBdqxQ?pwd=rvky)
- Extraction code: `rvky`
- Target tested by the owner: iPad Air 5 (M1).

The owner supplied this external link on 2026-10-29. The shared file has not
been independently downloaded or compared with the local verified artifact.

## Reproduction archive

Read [the recovery and rebuild runbook](reproduction/REPRODUCE.md) first.
It includes a source snapshot, eleven patches, overlays, Windows tools, tests,
compiler fingerprints and source checksums. This is not a tested one-click
clean-machine installer; see its explicit recovery gaps and external inputs.

## Result and scope

After installing build **P5R-M1-fix2**, the device owner reported that the game
now runs correctly, with working picture, sound and gameplay. The tested device
is an **iPad Air 5 with Apple M1**. The owner reported iPadOS 27.2; that version
was not independently read from the device.

The game build is **Persona 5 Royal 1.0.2**, title ID `01004B10157F2000`.
The IPA was built unsigned on Windows and signed and installed by the owner
using an on-device signing application.

This is an owner-reported successful play test, not a full-game certification.
No measured frame-rate benchmark, test duration, complete save/load matrix,
suspend/resume campaign, or full playthrough was recorded. iPhone 14 Pro/A16
was not validated; M1 success does not establish A16 texture compatibility.

## Failure progression

| Build stage | Observed behavior | Evidence and response |
| --- | --- | --- |
| Initial build | Settings opened; entering the game crashed | Surface allocation assertion exposed incorrect linear render-target sizing. |
| fix1 | Audio and frame presentation ran, but the picture was black | Device logs showed missing shader keys, no loaded shader libraries/pipelines, stamp parsing problems and some library-open failures. |
| fix2 | Owner reported correct graphics, sound and gameplay | Added executable-embedded shaders, rebuilt dependent shaders/tables, corrected text parsing and resource packaging, and added diagnostics. |

Several changes shipped together in fix2. The successful test does not isolate
the contribution of every packaging change.

## 1. A render-target flag can imply linear layout on its own

The startup trap was a game assertion in `SetupSurfaceInfoMemoryInside`:

```text
ctx.memorySize <= localmemsetupinfo.memorySize
```

The failing surface was 16 by 16, RGBA8, with an explicit stride of 128 bytes.
NVN's `LINEAR_RENDER_TARGET` flag (`0x40`) was set without `LINEAR` (`0x10`).
The host recognized only `0x10` and calculated a block-linear size of 1,024
bytes. The required linear allocation was `128 * 16 = 2,048` bytes.

The general correction treats either flag (`flags & 0x50`) as linear across
layout, mip offsets, sparse-layout exclusion and deswizzle handling. Ordinary
linear alignment is 32 bytes and render-target alignment is 128 bytes; explicit
stride must still be respected. A linear surface must not enter the
block-linear deswizzler.

Implementation lives in the fork's patch queue:

- `webui/patches/0010-nvn-linear-render-target-layout.patch`
- `webui/patches/0011-nvn-linear-render-target-deswizzle.patch`
- Regression: `webui/tests/test_linear_render_target.py`

The useful diagnostic lesson is to decode the failing assertion and compare
the game's requested layout against the host's calculation before attributing
a startup crash to insufficient device memory.

## 2. Asset shader extraction was incomplete

The first successful shader build covered **30,418** shaders from nine GSC
resources in CPK archives. Completion of that build did not prove coverage of
the shaders requested during execution.

The black-screen log identified **12 unmapped runtime keys**. All twelve were
matched byte-for-byte to shader records embedded in the game's `main` module.
A validated adjacent-record scan found **228 additional shaders**:

- 212 fragment shaders;
- 10 vertex shaders;
- 6 compute shaders.

Some records were aligned to four bytes and lacked the address-reference
patterns required by the existing reader. The added reader validates record
headers, lengths, bounds, stage and the control/code content key. It appends
packages while preserving existing package indices and merges compute
workgroup/shared-memory facts.

Adding shaders also changed varying coverage. **1,114 vertex keys** changed,
including 1,104 previously known vertices. Rebuilding only the twelve missing
keys would therefore have left incompatible derived output.

The full rebuild produced **30,646 shader keys** and regenerated `c1_full.tsv`
and `cb_extent.tsv` with the same input stamp. At the Metal-library level,
29,511 items were reused and 1,135 compiled. This is not a claim of that many
shader-build cache hits.

Implementation: `webui/tools/embedded_shader_packages.py` and
`webui/tests/test_embedded_shader_packages.py`.

For future bring-up, inspect both asset archives and executable modules, then
compare actual runtime requests against the packaged map. Recompute dependent
coverage and metadata after any input changes.

## 3. Windows line endings broke otherwise correct stamps

Windows-generated TSV files used CRLF. Splitting only at LF left a trailing
carriage return in game IDs and input digests. The runtime consequently
reported a library as belonging to another game even when the printed IDs
looked identical, and rejected guard/extent metadata as stale.

Text consumers in `nvn_mtl.m` now split using
`NSCharacterSet.newlineCharacterSet`. The fix preserves identity and freshness
checks; it does not bypass them. Shader maps, stamps, guards and pipeline text
need consistent handling of native line endings.

This change and resource diagnostics are maintained in the existing
`webui/patches/0006-nvn-mtl-spatial-upscaling.patch` overlay.

## 4. Large IPA packaging needs independent verification

In the earlier IPA, a large game archive preceded the shader files, placing
their ZIP offsets above 4 GiB. Small entries were also unnecessarily forced
into ZIP64 form. The device reported several known-key library-open failures,
although those files existed in the unsigned source IPA.

The installed bundle was not inventoried before fix2, so the exact cause of
those open failures is unconfirmed. In particular, this evidence does not
establish a defect in a particular signing application.

The replacement packer now:

1. Places small resources before large files, keeping shader local-header
   offsets below 4 GiB.
2. Uses ZIP64 only where the entry actually requires it.
3. Removes inherited ZIP64 extra field `0x0001` and resets small-entry ZIP
   versions before allowing the ZIP writer to regenerate required metadata.
4. Preserves executable permissions and verifies the content hash of every
   unchanged and replaced entry.

Copying `ZipInfo` alone is insufficient: it can preserve stale ZIP64 extras
and extraction-version fields even after `force_zip64` is disabled.

The host also logs the build label, installed shader-directory entry count,
and library-open errors with existence/size information. These distinguish
missing packaging, stale installs and shader translation failures.

Implementation: `webui/tools/replace_ipa_executable.py` and
`webui/tests/test_ipa_resource_update.py`.

## Toolchain and build discipline

The successful local setup used a Windows host, Python 3.13.16, .NET 10 SDK,
LLVM-MinGW, an iPhoneOS 26.5 SDK, and **Metal Developer Tools for Windows 6.2**
with inner compiler build **32023.850**. The host CPU target was `apple-m1`.

Use the pinned shader translator matching the chain lock. A fresh
`dotnet publish` is not a substitute. Keep tool versions and the generated
shader-chain header coherent; changing profile inputs requires a full shader
build, regenerated guard/extent tables and a rebuilt host.

The inner `metal/32023/bin/metal.exe` was used directly because the wrapper
mishandled arguments containing spaces in this setup. ASCII output paths
avoided native compiler problems with non-ASCII paths. Tools reading game
files can still use Unicode source paths.

The Windows staging setup also needed `c1_guard.py`, `cb_extent.py`, and the
generated `chain/gfx/nvn` directory. The provisional profile's `mem_used` was
adjusted from 64 MiB to `0x4c00000` (76 MiB) based on rewritten module size.
That value must be reassessed for another game build.

Keep general host fixes in the fork patch/overlay queue and game-specific
constants in the selected profile. Never reuse fixed addresses across NSO
build IDs without disassembly verification.

## Verification record

The final unsigned archive contained:

| Item | Verified value |
| --- | --- |
| Build label | `P5R-M1-fix2` |
| IPA bytes | 14,457,942,102 |
| Archive files | 88,823 |
| Shader keys | 30,646 |
| Metallib files | 58,147 |
| Highest metallib local-header offset | 787,451,949 bytes |
| Shader chain | `bcd8a8e27f1b` |
| Profile input stamp | `a051ae51b653` |

All twelve observed missing keys were present in the final map and libraries.
All archive entry contents were hash-verified. The Windows host build compiled
136 sources and its unsigned executable's embedded sections were checked.

Focused regression coverage includes the linear render-target calculation,
embedded-shader discovery and stable indices, repeat-run behavior, archive
resource replacement and stale ZIP64 metadata, corruption rejection, and the
patch queue. Native Apple GPU tests cannot execute on this Windows host.
Device validation is the owner's subsequent report, separate from build-time
verification reports created before that test.

## Related upstream reports and limits of analogy

These links record issues reviewed during bring-up; they are not evidence
that this fork includes every upstream fix:

- [BotW black/corrupt video with audio (#242)](https://github.com/seedds/nxnative/issues/242):
  similar symptoms warrant checking toolchain and shader coherence, but do not
  identify the cause of this P5R failure.
- [BotW version-dependent missing shaders (#251)](https://github.com/seedds/nxnative/issues/251):
  match the game version and module build IDs before reusing a profile.
- [TotK memory-shortage Blood Moon (#70)](https://github.com/seedds/nxnative/issues/70):
  an SDK address-region problem is distinct from P5R's surface-size assertion;
  its build-specific SDK patch must not be copied blindly.
- [Upload staging growth (#147)](https://github.com/seedds/nxnative/issues/147)
  and [#164](https://github.com/seedds/nxnative/issues/164):
  relevant to future long-session memory tests. The upstream backpressure fix
  was reviewed but was not included in this local fix2 build.
- [TotK terrain rendering (#183)](https://github.com/seedds/nxnative/issues/183):
  attachment/output type issues require evidence from the affected pipeline;
  globally forcing integer outputs is not an appropriate preventive change.

## Practical checklist for the next title or update

1. Record the game version, module build IDs, device GPU, system version and
   exact toolchain before building.
2. Separate boot/assertion failures from shader lookup, library loading,
   pipeline creation and draw-output failures using device logs.
3. Survey executable and archive shaders; validate actual runtime coverage.
4. Regenerate all derived shader metadata after changing inputs, then build
   the host against that same chain.
5. Check archive hashes, ZIP metadata, installed resource availability and
   the runtime build label before diagnosing a stale or incomplete install.
6. Test picture, audio and gameplay on the target device; record extended
   save/load, suspend/resume and memory behavior separately.

This report contains no game executables, extracted shader bytes, game assets,
decryption keys, proprietary SDK files or raw device logs. The IPA link above
points to an external file shared by the owner.
