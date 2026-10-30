# Repository review

**Publication update — 2026-10-30:** local paths and probe serial values are
redacted in the public evidence; offsets 56–63 of each historical RAM record
are zeroed and labeled in a hash manifest. Unmodified originals and original
Git history are retained privately. The owner selected MIT for original work.
Current firmware source initializes both reserved words. See
[PUBLICATION.md](PUBLICATION.md) for verification and the history-free export.
Earlier Git commits remain unredacted; publishing this checkout's existing
history would still disclose the earlier material.

**Historical technical-review verdict: READY WITH MINOR CAVEATS.** The
technical checks below describe the earlier review, before publication
sanitization. Neither that review nor this publication preparation committed,
pushed, changed visibility or accessed the STM32 device.

## Scope and changes

The review began with a clean checkout at `096f0960627d5341d9ad0b50349108b7ba5b7490` (`Initial commit`) on `validation/mlkem-host-board`. The configured origin was `https://github.com/joeywwong/ml-kem-m4.git`; local history contained one reachable commit. Historical statements about no commits, no remote and no push describe the earlier experimental session, not this later state.

The earlier review added the root README, version-controlled ignore rules and this review. It updated `MLKEM_BOARD_PROGRESS.md`, `validation/README.md` and `validation/COMMANDS.md` to clarify chronology, reproduction and hardware identification. Its only executable-code change was in `scripts/run_host.py`: optional `MLKEM_BUILD_DIR` / `MLKEM_EVIDENCE_DIR` overrides, creation of nested output directories, and reuse of archived public coins for fresh output directories. Defaults remain compatible with the original scripts. That review changed no cryptographic code, firmware source, linker map, measurement algorithm or original evidence. Later publication changes are recorded above and in PUBLICATION.md.

The historical [source-hash manifest](evidence/source-hashes.json) remains intact: its `run_host.py` hash describes the original script before output routing, and its `validation.c` hash precedes reserved-word initialization. The other seven listed sources retain their original identity. Earlier fresh checks used ignored `validation/build/review-audit/`; public evidence transformations now have a separate [manifest](evidence/redaction-manifest.json).

## Issues and disposition

| Issue | Severity | Resolution | Remaining limitation |
|---|---|---|---|
| No root overview; stale Git-state claims | Low | Added evidence-linked README and explicit historical scope | Git state is a dated local snapshot |
| Reruns overwrite named evidence/build outputs | Medium | Added and exercised output overrides; documented host-only workflow | Defaults still overwrite outputs; use fresh override directories |
| VE marking report conflicts with 1 MiB register observation | Medium | Documented direct observations versus uncertain physical identification | No committed photo; resolve before future programming |
| Exclusions existed only in `.git/info/exclude` | Medium | Added `.gitignore`; verified no tracked files match exclusions | Ignore rules cannot remove history or prevent forced addition |
| Local paths and probe serial in recorded logs/history | Medium | Public copies redacted; originals retained privately; history-free export provided | Existing local/remote history is not sanitized |
| Two uninitialized reserved words in raw RAM reports | Low | Public copies mask exactly eight bytes; current firmware initializes both words | Historical measurements still describe the original image |
| No license for original code/documentation | Low | Owner selected MIT; root license and third-party attribution added | Third-party terms remain applicable |
| ELF/debug-file size can be confused with flash usage | Low | README reports 29,608-byte binary, 6,064-byte static SRAM, separate stack reservation | Stack watermark is approximate, whole-harness only |
| Measurement and assurance limits | Informational | Distinguished 100 unique inputs from 300 observations per operation; identified timed valid-ciphertext path | No entropy integration, leakage study, attack or certification |

The harness checks return codes, roundtrip equality, repeated rejection, selected malformed-key errors and host/device secret agreement. The recorded rejection secrets independently satisfy SHAKE256. The ELF validator checks ARM ELF32, virtual/load bounds and entry range; the hardware runner separately checks exact binary/file-backed-segment correspondence and backup consistency. These checks target this generated image, not arbitrary hostile ELF files or exhaustive API validation. No high-confidence defect invalidating the existing measurements was found. The runner's family/flash checks do not resolve the physical marking discrepancy, and interrupted hardware recovery remains possible.

One harness hygiene defect was found: the historical firmware did not initialize `struct report.reserved[2]` in [src/validation.c](src/validation.c). [src/startup.S](src/startup.S) clears only BSS, while [src/stm32f407vg.ld](src/stm32f407vg.ld) places `.results` in a separate NOLOAD section. Offsets 56–63 in each original `hardware-run-*.bin` therefore contained residual SRAM of unknown origin. These fields are ignored by decoding and validation and lie outside the cycle array, so this does **not** invalidate the reported tests, timing or stack results. Publication preparation masked exactly these bytes in labeled public copies and added initialization before the report header in current source. The new firmware needs its own hardware evidence; historical firmware hashes and measurements were not replaced.

## Checks actually executed in the earlier technical review

Host tools: Python 3.13.7, MinGW GCC 13.2.0; cross-build: ARM GCC 14.3.1. `run_host.py`, `run_acvp.py` and `build_board.py` used `MLKEM_BUILD_DIR=validation/build/review-audit/build` and `MLKEM_EVIDENCE_DIR=validation/build/review-audit/evidence`. No hardware runner was executed.

| Check | Result |
|---|---|
| Fresh upstream functional suites | PASS: default 1,000 iterations each for ML-KEM-512, 768 and 1024 |
| Fresh host corpus | PASS: 100 roundtrips, malformed-public/secret-key checks, repeated rejection and independent SHAKE256 checks; corpus output matches archive byte-for-byte |
| Fresh pinned NIST ACVP run | PASS: 75 + 165 + 195 = 435 cases; summary matches archive |
| Source/vector verification | PASS: both upstream pins match with no tracked modifications; all six vector hashes match |
| Offline ARM build | PASS after sandbox retry; first launch failed with Windows error 623 before compilation |
| Firmware comparison | PASS: rebuilt binary SHA-256 `74f75ccd62735f2e2fcdb4d6c0f3fce4ca8f9bc753a4b81a27a813cf5602693e` matches the historical image |
| ELF validator suite | PASS: all five tests on original ELF; all five on rebuilt ELF |
| Original ELF identity | PASS: matches archived SHA-256 `736fed9f86e86b43cc79e62e41dbfaf7afb64001fc3915ca8093c503cbd21a75` |
| Raw hardware evidence consistency | PASS: three 1,264-byte records decode to JSON; all 900 cycle values and all medians/ranges match; each watermark is 18,132 bytes |
| Original corpus verification | PASS: 100 unique 96-byte inputs, correct coin hash and 100 independent rejection-formula checks |
| Evidence preservation | PASS: all 93 original evidence files unchanged byte-for-byte |
| Git/diff/links/ignore checks | PASS: no whitespace errors, local Markdown targets/anchors resolve, no tracked files ignored; generated/private paths covered |
| Publication scan | 106 tracked files and the sole reachable commit examined; no credential-pattern matches or private firmware dumps found; identifying metadata remains below |
| Hardware execution, flashing, reset, recovery rerun | NOT RUN: expressly excluded from this review |
| Clean network fetch on a new machine / other host platforms | NOT RUN: existing pinned dependencies used; documented Windows commands checked locally |

The rebuilt ELF hash differs because the build directory changed and the ELF includes debug information. Its flash binary is identical; the rebuilt ELF is not substituted for the recorded hardware ELF. New logs and checks remain under the ignored review directory. The original hardware PASS statuses remain historical observations, not new device tests.

## Publication metadata and history

Before sanitization, recorded logs contained local installation/user paths and 44 programmer logs contained an ST-Link serial field. These included [the command ledger](evidence/commands.jsonl), [board identification](evidence/board-identification.txt), `hardware-poll-*.txt`, and flash/restore logs. Paths also appeared in the historical command guide and size/objdump reports. Public copies now replace these values with placeholders. The probe serial identifies a debug probe; family ID `0x413` and CPUID are not unique device identifiers. No MCU unique-ID capture was identified. Earlier Git metadata contains the author's name and institutional email address. Changing working-tree files does not remove earlier content or metadata from history; use the history-free export for clean publication.

No credentials, access tokens, private-key PEM blocks or original-firmware dumps were found by targeted content/pattern inspection. This is a bounded audit of locally available history, not a guarantee about inaccessible remote refs, deleted remote objects or every possible secret encoding. The four tracked binary files are three decoded RAM result blocks and the 9,600-byte public test-coin fixture. Derived shared/rejection secrets in `host-corpus.jsonl` are deliberate public test data. The three full-flash backup/readback files remain local and ignored; their hashes and recovery logs are retained as evidence. No vendored upstream source or generated executables are tracked.

The recommended public-copy redaction has now been performed: originals are private, placeholders are consistent, exactly eight reserved bytes per binary are masked, and each evidence file is labeled with original/public hashes and transformations in the manifest. Commands, return/status text, device-family/register values, measurements and firmware hashes are preserved apart from the documented metadata substitutions. No history rewrite was performed. The export omits all Git metadata and earlier unredacted objects.

## Licensing and attribution

The pinned mlkem-native [LICENSE](https://github.com/pq-code-package/mlkem-native/blob/08e1f3881ec140f79c2d1c14e482a32a782c5312/LICENSE) identifies the library as derived from the public-domain Kyber reference implementation and licenses `mlkem/*` / `dev/*` under Apache-2.0 OR ISC OR MIT. Test RNG code and other auxiliary files have their own SPDX terms; upstream documentation uses CC-BY-4.0. Fetched notices remain intact. pqm4 was inspected only, not compiled into this firmware; its pinned README describes component-specific licenses. NIST vectors are fetched from the pinned official source and hash-checked, not vendored here.

At the owner's selection, the original harness, scripts and documentation now use the root [MIT license](../LICENSE). [Third-party attribution](../THIRD_PARTY_NOTICES.md) preserves the scope of upstream terms. Any later redistribution of compiled firmware or upstream source should retain applicable upstream notices; no compiled release artifact was added here.

## Remaining owner steps

1. Review the sanitized files and [publication notes](PUBLICATION.md).
2. Publish from the verified history-free export using fresh history and the desired public author metadata. Do not expose this checkout's earlier history as if it had been sanitized.
3. Keep the private snapshot and original firmware backups private; do not force-add ignored paths.
4. Ensure any shared URL opens the intended public snapshot and its root README. No push or visibility change was performed here.

No additional board run is needed for sharing this documented experiment. Resolve physical part identification before any future programming, and describe future side-channel work as planned.
