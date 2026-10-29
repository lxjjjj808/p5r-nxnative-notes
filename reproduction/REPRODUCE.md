# P5R M1 recovery and rebuild runbook

Updated: 2026-10-29. Start here when returning to this work.

## What this archive can and cannot reproduce

`reproduction/source/` contains the fork-side source snapshot, patches,
overlays and tests. Copy its contents over a separate nxnative checkout;
do not apply patch files directly to the working checkout. Build from a stage.
The source snapshot includes existing fork code as well as this session's
changes; it is not a minimal upstream pull request.

`reproduction/SHA256SUMS.json` inventories every preserved file. The original
project's MIT licence is retained in `reproduction/source/LICENSE`.

This is a recovery runbook with source evidence, not a tested clean-machine
one-click installer. The historical shader preparation and host build passed,
and the owner confirmed fix2 gameplay on M1. The complete process below has
not been rerun from original NSPs after publication. Do not claim otherwise.

## Identity: reject mismatching inputs

| Input | Historical successful value |
| --- | --- |
| Title ID | `01004B10157F2000` |
| Update package/display version | `v65536` / `1.0.2` |
| main build ID (16-byte form used by profile) | `d4b150b29a931cd381e2a30318fc299f` |
| subsdk0 build ID | `a8cb97803f7f442a3b6cce1c7cd4ee4a` |
| sdk build ID | `357efc198e728cb5d55265aff304f03c` |
| CPU target / host deployment target | `apple-m1` / `arm64-apple-ios26.0` |
| Metal inner compiler | `32023.850`, Windows tools 6.2 |
| Shader chain / profile input digest | `bcd8a8e27f1b` / `a051ae51b653` |
| Final unsigned host SHA-256 | `e7d7caaee5f283123d622769f2ed546d49f366f99f778bf0ffe74f98c1451747` |

Read `reproduction/source/webui/patches/UPSTREAM_BASE` for historical source
commit anchors. It records upstream base `fa69e20a280413d56e64edcb8736bf9329957f77`
and fork anchor `c586dd15b01e52cb7a31732163786ab4a54101b9`.
The old workspace was a ZIP checkout, not a Git checkout. Those anchors are
provenance, not proof that an arbitrary current `main` matches the old tree.
`reproduction/baseline-source-sha256.json` fingerprints the local `dm/` and
`scripts/` source inputs, excluding generated/binary payloads. Compare these
before interpreting an apply failure as permission to relax patch matching.

The captured Windows chain lock is in `reproduction/evidence/windows-chain.lock`.
Its explicit executable hashes are authoritative; its generic `spirv-cross`
field says `missing` because upstream discovery used a different command name.
Do not replace the actual hashed executable with a guessed newer build.

## External inputs and local recovery state

Supply the same base/update game files, your own required keys, the pinned
translator DLLs, SPIRV-Cross, Metal tools, LLVM-MinGW, iPhoneOS SDK, Python
packages and fonts yourself. Generated shader bytes and game modules are not
included in this public source archive.

Use placeholders below, replacing them with actual paths. Keep large build
outputs on a data drive. `Repo` means the restored checkout, `Stage` its
patched copy, `Work` the external profile/packages directory, `Build` the
shader/host output directory, and `Extract` the matching extracted ExeFS/RomFS.

At the 2026-10-29 audit, the historical game work directory and its external
final profile were no longer found at their recorded location. The saved task
profiles still exist but are **provisional, pre-fix profiles**; do not silently
reuse them as the final one. The retained final IPA, verification JSON, M1 host
and Metal output are the best local recovery anchors. Use the final IPA's
Info.plist and metadata plus this runbook to check recovered configuration.
The machine-specific locator is saved separately on the original computer,
not in this public repository.

## Route A: recover from retained verified artifacts

1. Preserve `P5R-M1-fix2.ipa` and its adjacent `.verification.json`. Confirm
   14,457,942,102 bytes, 88,823 entries, 30,646 shader keys and 58,147 metallibs.
   Compare each entry SHA-256 against `file_sha256` in the report before reuse.
2. Preserve `m1-host/DmIOS` and `link_report.json`. Its hash must match the
   value above; `signed` must be false and `ios_platform` must be 2.
3. Preserve `metal-sample/chain`, `mac`, `ios`, and the relevant compiler
   binaries. Do not run a new prepare step over the only surviving chain.
4. To replace the executable in an otherwise unchanged verified archive:

```powershell
python "$Stage/webui/tools/replace_ipa_executable.py" `
  --source "$Build/P5R-M1-fix2.ipa" --host "$Build/m1-host" `
  --out "$Build/P5R-M1-recovery.ipa"
```

This command reads the adjacent source verification JSON and verifies all
copied entries. It does not repair missing shaders. To replace resources too,
pass `--resources-manifest`: a JSON object mapping full archive entry names
such as `Payload/DmIOS.app/dm/shader_map.tsv` to local replacement file paths.
The final archive must keep map, libraries, input stamp and guard tables
coherent. A new output file is required; never overwrite the only good IPA.

## Route B: rebuild from matching original inputs

### Restore and stage source

Restore the historical fork baseline, overlay `reproduction/source/`, install
the dependencies in its `webui/requirements.txt`, and supply `cricodecs` for
CPK extraction. Exact Python package versions beyond the captured metadata
are not fully locked; record them with `python -m pip freeze` on recovery.

```powershell
Set-Location $Repo
$env:NX_STAGE_ROOT = "$Build/stages"
$env:NX_STAGE_KEEP = '100'
python -c "from webui.staging import ensure; print(ensure(keep=100))"
```

Record the returned path as `Stage`. Staging may garbage-collect older stages;
using a separate root prevents touching historical recovery artifacts.

### Extract, profile and rewrite

Use the fork's existing survey/extraction workflow for the base plus update,
with user-provided keys. Inspect `build_ipa_windows.py` for the extraction
invocation, but **do not use its generic shader-split phase as a complete P5R
pipeline**: P5R required the explicit GSC and embedded-main steps below.

Keep the provisional profile as a starting point only. The recorded layout is
`mem_reserve=0x100000000`, `mem_alias=0x10000000`,
`mem_stack=0x10000000`, `app_pool=0xCD500000`, `sys_resource=0`;
the corrected `mem_used` is `0x4c00000`. Use modules `main subsdk0 sdk`, package
`v65536`, RomFS marker `CPK/ALL_ASIA.CPK`, and store `.cpk:.metallib` entries.
Set these in the external profile and validate all build IDs before rewriting.

```powershell
$env:DM_GAME = $Profile
$env:DM_ROOT = $Work
$env:PYTHONUTF8 = '1'
foreach ($module in @('main','subsdk0','sdk')) {
  python "$Stage/dm/tools/patch_nso.py" "$Extract/ExeFS/$module" $Patched $module
  if ($LASTEXITCODE -ne 0) { throw "Rewrite failed: $module" }
}
python "$Stage/webui/build/windows/verify_nso_rewrite.py" `
  "$Extract/ExeFS" $Patched main subsdk0 sdk --report "$Build/rewrite.json"
```

Do not import TotK's SDK 20 memory patches into this SDK 13 game.

### Extract all shader sources before compiling

Inspect CPK entries through `cricodecs.cpk.load(path).file_infos()` and extract
the `.GSC` entries with `file_bytes(index)` into a flat scratch directory.
Preserve unique filenames; refuse collisions. Historical input had nine GSC
resources. `cpk_asset_survey.py` assists discovery but is not an extractor.

```powershell
python "$Stage/webui/tools/gsc_shader_packages.py" $GscDirectory `
  --profile $Profile --out "$Work/gsc-shaders"
Copy-Item "$Work/gsc-shaders/tables/*.tsv" $Profile
python "$Stage/dm/tools/nso.py" "$Extract/ExeFS/main" "$Work/main-original.bin"
$OriginalMainImage = "$Work/main-original.bin"
python "$Stage/webui/tools/embedded_shader_packages.py" `
  --image $OriginalMainImage --profile $Profile `
  --packages "$Work/gsc-shaders/packages"
```

`OriginalMainImage` is the original **decompressed mapped module image**, not
the compressed NSO container and not a rewritten module. `dm/tools/nso.py`
writes that mapped image, including the BSS area. Check its layout
against the raw-image preparation used for binary analysis before scanning.
This intermediate is private and is not distributed here.

Expect 30,418 GSC shaders, then 228 additions (212 fragment, 10 vertex,
6 compute), for 30,646 total. Preserve `embedded-additions.json`: its
`affected_vertex_keys` lists 1,114 vertices requiring regeneration. Any count
mismatch is a checkpoint failure requiring investigation, not a number to
force into a manifest.

```powershell
python "$Stage/webui/build/windows/windows_shader_build.py" `
  --profile $Profile --packages "$Work/gsc-shaders/packages" `
  --out "$Build/metal-sample" --metal $MetalInnerExe `
  --spirv-cross $SpirvCrossExe --dotnet $DotnetExe `
  --cache-dir "$Build/shader-cache" --jobs 8
```

Run the full build without selecting only the twelve runtime-missing keys.
Use ASCII output paths and the inner Metal binary. A changed tool path can
change generated chain sources and identity; restore original paths through
a compatibility junction only after verifying binary hashes, or rebuild the
entire coherent chain and host under the new identity. Never relabel old libs.

Require all 30,646 status rows to be `ok`; match `inputs.tsv` with both
`c1_full.tsv` and `cb_extent.tsv` headers. Historical bounded-read proof had
zero unproven shaders; the extent table reported 133,271 bounded uniform
slots, nine read-only storage slots and 30,589 shader rows. A library count
alone is not success.

### Build host and package

```powershell
python "$Stage/webui/build/windows/ios_cross_compile.py" `
  --clang $ClangExe --sdk $Sdk --profile $Profile `
  --out "$Build/m1-host" --cpu apple-m1 --jobs 8
python "$Stage/dm/ios/tools/gen_embed.py" $Patched `
  "$Build/m1-host/embed.S" main subsdk0 sdk
```

Capture `gen_embed.py` stdout as UTF-8 `embed_link_flags.txt` (avoid Windows
PowerShell 5's default UTF-16 redirection). Assemble `embed.S` with the same
Clang, target `arm64-apple-ios26.0`, SDK and `-mcpu=apple-m1`; write `embed.o`.
Then run `ios_cross_link.py --lld $LldExe --sdk $Sdk --build "$Build/m1-host"`.
See `build_ipa_windows.py` for the precise argument arrays.

Use `ios_cross_pack.py --profile $Profile --host "$Build/m1-host" --patched
$Patched --romfs "$Extract/RomFS" --shaders "$Build/metal-sample/ios" --font
$StandardFont --letter-font $LetterFont --out $FirstIpa --experimental`.
All options are on one logical command; add an icon only if present.

The base packer is not the final ZIP64 compatibility pass. Prepare a replacement
manifest with updated `Info.plist` (`DMBuildLabel=P5R-M1-fix2`,
`DMShaderCount=30646`), `dm/env.txt` (`DM_NVN_SHDUMP=temp`), shader map,
guard/extent tables, matching `msl/b-<chain>/inputs.tsv` and every changed or
added `_b`, `_bf`, `_bv` library/reflection pair. The original manifest
preparation script is retained in `reproduction/recipes/prepare-fix2-resources.py`
with machine-specific paths replaced by environment inputs. For a fresh chain,
replace **all** libraries and the executable; this incremental historical
recipe assumes a verified compatible source IPA and must not mix chain IDs.

Run `replace_ipa_executable.py` on the verified first IPA with the manifest.
It orders small entries before large ones, strips inherited ZIP64 metadata,
preserves permissions and hash-checks all entries. Verify shader offsets below
4 GiB and small-entry extraction version 20 with no stale ZIP64 extras.

## Tests and acceptance gates

From the restored checkout:

```powershell
python -m unittest webui.tests.test_embedded_shader_packages `
  webui.tests.test_ipa_resource_update webui.tests.test_patch_queue `
  webui.tests.test_linear_render_target
```

Eight tests passed on the original Windows machine. The linear-layout test
needs native Windows Clang; a skipped test is not a passing native check.
Set `NX_TEST_CLANG` when that compiler is installed elsewhere.

Inspect `DMBuildLabel`, selected M1 device, map/stamp acceptance and installed
shader-directory count in returned device logs. Require shader/pipeline loads,
visible scene rendering, sound and gameplay. Missing keys, `cannot open`,
pipeline errors or red lines require investigation. Test save/load and
suspend/resume separately; no full-game or A16 certification exists.

## Handoff rules for the next assistant

- Read this file and the main postmortem before changing anything.
- Verify retained artifacts and current paths. Old paths are historical hints.
- The missing original work directory is a real recovery gap; ask for matching
  original inputs if they cannot be located, rather than pretending it exists.
- Keep the final known-good IPA and its report until a new device test passes.
- Report shader build, IPA build and device play test as separate milestones.
- A clean rebuild may be functionally equivalent without being byte-identical;
  generated timestamps, paths and new chain identity affect hashes.
