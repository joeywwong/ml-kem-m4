# ML-KEM-768 on STM32F407: Functional Validation and Benchmarking

## Overview

This repository records real ML-KEM-768 execution on a tested STM32F407 board, identified by its owner as an STM32F407G-DISC1, using the unmodified portable C backend of mlkem-native. ML-KEM is NIST's standardized lattice-based key-encapsulation mechanism for establishing shared secrets in post-quantum cryptography. Embedded execution makes implementation cost and resource constraints concrete: this project connects host correctness tests to on-device checks, cycle measurements, and memory accounting. The completed experiment passed host functional suites for all three parameter sets, 435 NIST ACVP cases, and 100 ML-KEM-768 inputs repeated over three hardware runs. It also recorded restoration of the original firmware. The contribution is the validation harness, reproducibility record, and analysis of this configuration. It provides preparation for cryptographic implementation and future physical side-channel research; no leakage acquisition or attack was performed.

## What this project demonstrates — short summary

This project demonstrates reproducible validation and benchmarking of ML-KEM-768 on an STM32F407 Cortex-M4 using unmodified mlkem-native code. It connects host tests and NIST ACVP vectors to on-device shared-secret checks, measures cycle counts and memory use, and records restoration of the original firmware. It provides a foundation for future physical side-channel research; no leakage measurements or attacks were performed.

## Objectives

- Preserve upstream source identity and use deterministic inputs to compare host and device behavior.
- Check shared-secret agreement, selected malformed-key errors, and implicit rejection.
- Measure operation cycles and memory use with explicit instrumentation limits.
- Validate firmware memory ranges and retain evidence of original-firmware recovery.

## Implementation

| Component | Recorded configuration |
|---|---|
| Cryptography | [mlkem-native](https://github.com/pq-code-package/mlkem-native/tree/08e1f3881ec140f79c2d1c14e482a32a782c5312), commit `08e1f3881ec140f79c2d1c14e482a32a782c5312`; portable C, no native backend |
| Parameter set | ML-KEM-768 on hardware; 512/768/1024 on host |
| Target | STM32F407 / Cortex-M4; tested with 1 MiB flash mapping and 128 KiB main SRAM; CCM unused |
| Toolchains | Python 3.13; MinGW GCC 13.2.0; ARM GCC 14.3.1 (GNU Tools for STM32 14.3.rel1); CubeProgrammer 2.23.0 |
| Build | `-O2 -mcpu=cortex-m4 -mthumb -mfloat-abi=soft`, section garbage collection; no LTO |
| Test inputs | 100 persisted 96-byte inputs: 64 bytes for `keypair_derand`, 32 for `enc_derand`; originally generated with `os.urandom` |

The upstream cryptographic source remains unmodified to preserve attribution and make the tested implementation identifiable. [Provenance](validation/provenance.json) pins sources and vector hashes; pqm4 was inspected for context but is not linked into this firmware. **The physical VE/VG marking remains unresolved:** the recorded flash-size register reports 1 MiB, but this does not prove a VGT6 package. See [hardware identification](validation/README.md#hardware-identification-and-scope).

## Validation

These statuses describe the original recorded experiment, not certification.

| Check | Status | Evidence |
|---|---|---|
| Upstream host functional suites, 1,000 iterations per parameter set | PASS | [512](validation/evidence/functional-512.txt), [768](validation/evidence/functional-768.txt), [1024](validation/evidence/functional-1024.txt) |
| NIST ACVP: 75 keygen + 165 encap/decap + 195 tr1 cases | PASS | [435-case summary](validation/evidence/acvp-summary.json) |
| Host corpus: roundtrips, malformed-key checks, repeated rejection and independent SHAKE256 fallback check | PASS | [100-case summary](validation/evidence/host-summary.json) |
| Device: same 100 inputs across three reset-started runs, host/device secret agreement | PASS | [Hardware summary](validation/evidence/hardware-summary.json) |
| ELF bounds / full original-flash restoration and restart | PASS | [ELF](validation/evidence/elf-validation.json), [restoration](validation/evidence/restoration.json) |
| QEMU, UART capture, hardware entropy integration | NOT RUN | SWD collection and public deterministic test coins were used |
| Power/EM acquisition, attacks, countermeasure evaluation | NOT RUN | Outside the completed experiment |

A modified full-length ciphertext returns success with a deterministic implicit-rejection secret, checked on host against `SHAKE256(z || c, 32)` and compared on device to the host result. Invalid public-key coefficients return −4; a corrupted embedded public-key hash returns −5. These selected checks do not exhaust malformed inputs. Wrong-sized buffers violate this fixed-size API's preconditions and were not passed.

## STM32 Benchmark Results

| Timed operation | Median cycles | Minimum–maximum |
|---|---:|---:|
| Deterministic key generation (`keypair_derand`) | 1,444,249.5 | 1,443,217–1,536,251 |
| Deterministic encapsulation (`enc_derand`) | 1,515,464 | 1,514,433–1,598,018 |
| Valid-ciphertext decapsulation (`dec`) | 1,874,357.5 | 1,873,341–1,956,975 |

There are **100 unique inputs, repeated three times**, yielding 300 observations per operation. DWT CYCCNT surrounds the API calls. The nominal configured clock is HSI16 at 16 MHz with AHB /1; recorded `RCC_CFGR=0` and `FLASH_ACR=0` indicate zero flash wait states and disabled flash caches/prefetch. Interrupts are disabled. Counts include call/barrier overhead and API zeroization, exclude input generation, and discard no warm-up samples. SWD polling may perturb timing; clock frequency was not measured externally. Rejection/error-path calls were checked but not benchmarked separately.

| Resource | Recorded size |
|---|---:|
| Flash binary, including startup, harness and test data | 29,608 bytes |
| Static main SRAM (`.results` + `.bss`; `.data` is empty) | 6,064 bytes |
| Whole-harness stack high-water mark, each run | 18,132 bytes |
| Reserved stack (additional to static SRAM) | 32,768 bytes |

The stack watermark is an estimate, not a per-operation bound. Debug sections and the ELF file's total size are not firmware flash usage. Sources: [section sizes](validation/evidence/firmware-size.txt), [ELF load segments](validation/evidence/elf-validation.json), and [raw runs](validation/README.md#evidence-and-commands).

## Reproducing the Results

From the repository root, use Python 3, Git and host GCC on `PATH`. The recorded workflow is Windows/PowerShell; other platforms are not verified. These commands fetch pinned dependencies and run **host-only** checks, saving new outputs under ignored `validation/build/`:

```powershell
$env:MLKEM_BUILD_DIR = 'validation/build/reproduce/build'
$env:MLKEM_EVIDENCE_DIR = 'validation/build/reproduce/evidence'
New-Item -ItemType Directory -Force $env:MLKEM_EVIDENCE_DIR | Out-Null
python validation/scripts/fetch_upstream.py
python validation/scripts/run_host.py
python validation/scripts/run_acvp.py
```

Stop if any command exits nonzero. Do not use `python -O`. The persisted public test coins are copied into a new output directory. Once dependencies are present, host tests need no network. See the [detailed guide](validation/README.md) for optional offline ARM compilation and ELF checks. Hardware execution overwrites firmware and requires separate board identification, a verified private backup, and explicit approval; it is not part of this host workflow. Do not apply the recorded hardware commands to an unverified board.

## Repository Structure

- [validation/src/](validation/src/) — validation harness, startup assembly and linker script.
- [validation/scripts/](validation/scripts/) — dependency fetching, host checks, cross-build, ELF tests and separately gated hardware runner.
- [validation/evidence/](validation/evidence/) — labeled public evidence, public inputs, masked RAM records and unchanged measurement summaries.
- [validation/provenance.json](validation/provenance.json) — pinned upstream commits and NIST vector hashes.
- [MLKEM_BOARD_PROGRESS.md](MLKEM_BOARD_PROGRESS.md) and [validation/COMMANDS.md](validation/COMMANDS.md) — historical outcome and executed-command ledger.
- [validation/REVIEW.md](validation/REVIEW.md) — repository audit, publication caveats and fresh verification results.

Fetched sources, build outputs and private firmware backups are excluded by [.gitignore](.gitignore).

## Limitations and Future Work

No power/EM traces were captured, no side-channel or key-extraction attack was demonstrated, and no physical countermeasure was evaluated. Cycle benchmarks do not establish side-channel resistance. Hardware entropy integration for randomized production use was not implemented. The deterministic coins and derived test secrets are public testing material, never production randomness or keys. Passing these tests is not FIPS certification or a complete assurance argument.

Future work could add independently validated entropy integration, physical leakage acquisition, attack evaluation and countermeasure benchmarking. Those are planned directions, not completed experiments. Hardware conclusions apply only to the tested configuration.

The original harness, scripts and documentation use the [MIT license](LICENSE).
Third-party terms remain intact; see [attribution](THIRD_PARTY_NOTICES.md).

Recorded local paths and ST-Link serial values have been redacted, and eight
unused bytes per historical RAM record have been zeroed. All 900 cycle values
and measurement summaries are unchanged. See the [evidence manifest](validation/evidence/redaction-manifest.json)
and [publication guide](validation/PUBLICATION.md). The current firmware source
initializes those bytes; the benchmark tables describe the historical image.
On 2026-10-30, the default branch was replaced with clean history beginning
at the sanitized snapshot. The local checkout follows that cleaned history.
Original history remains in the ignored private backup; previously shared
copies and cached commits may still exist. See the publication guide for details.

## References

- [NIST FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard](https://csrc.nist.gov/pubs/fips/203/final).
- [mlkem-native at the tested commit](https://github.com/pq-code-package/mlkem-native/tree/08e1f3881ec140f79c2d1c14e482a32a782c5312).
- [NIST ACVP vectors at the pinned commit](https://github.com/usnistgov/ACVP-Server/tree/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files).
- [ST UM1472: Discovery kit with STM32F407VG MCU](https://www.st.com/resource/en/user_manual/um1472-discovery-kit-with-stm32f407vg-mcu-stmicroelectronics.pdf).
- [ST RM0090: STM32F4 reference manual](https://www.st.com/resource/en/reference_manual/rm0090-stm32f4xx-reference-manual-stmicroelectronics.pdf).
