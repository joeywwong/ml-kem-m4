# ML-KEM board validation results

This is the outcome of the original experimental session. For the current project overview and later repository review, see [README.md](README.md) and [the review record](validation/REVIEW.md). Git-status statements below are explicitly scoped to that session.

**PASS: real ML-KEM-768 executed on the STM32F407G-DISC1.** This is a functional implementation/benchmark update. The prerequisite GF(2) milestone was confirmed finished and reviewed by the user. Original firmware was restored, verified over all 1,048,576 flash bytes, and restarted after testing.

**Provenance.** Unmodified [mlkem-native](https://github.com/pq-code-package/mlkem-native/tree/08e1f3881ec140f79c2d1c14e482a32a782c5312), commit `08e1f3881ec140f79c2d1c14e482a32a782c5312`, portable C backend. [pqm4](https://github.com/mupq/pqm4/tree/6ff2be970f6f4592b341d432042063ceacf424a2) was inspected at `6ff2be970f6f4592b341d432042063ceacf424a2`; its notice says active maintenance has ended, with archival planned in/after January 2027. Its Discovery target assumes F407VG/1 MiB, so it was not applied to an unverified VE device. NIST ACVP release v1.1.0.43 is pinned to `975de31eb83d87039ec88934fdc47d8c312b892d`; all six JSON files have recorded SHA-256 hashes.

**Board/build.** User identified STM32F407G-DISC1; ST documents an F407VGT6 for that board model. An earlier user report suggested a VET6 marking; no photograph or definitive package identification is committed. SWD read device ID `0x413`, flash-size register `0x0400` KiB, and Cortex-M4 CPUID `0x410fc241`. Neither the family ID nor the 1 MiB register reading proves the physical part is VGT6. The result applies to the tested board configuration; see [identification scope](validation/README.md#hardware-identification-and-scope). Linker limits: flash `0x08000000–0x080FFFFF`, main SRAM `0x20000000–0x2001FFFF`; separate 64 KiB CCM unused. All ELF load ranges and flash image bytes checked before programming. ARM GCC 14.3.1 (GNU Tools for STM32 14.3.rel1), `-O2 -mcpu=cortex-m4 -mthumb -mfloat-abi=soft`, section GC, no LTO/native backend; STM32CubeProgrammer 2.23.0. Host: MinGW GCC 13.2.0, `-O2`.

| Validation | Final status / evidence |
|---|---|
| Upstream host functional suites | **PASS** — default 1,000 iterations each for 512/768/1024 |
| Independent NIST ACVP vectors | **PASS** — 435 host cases across all three parameter sets |
| ML-KEM-768 corpus | **PASS** — 100 OS-generated test inputs; roundtrip, malformed-key returns, repeated rejection; fallback secret independently checked with Python SHAKE256 |
| Cross-build / ELF bounds | **PASS** — 29,608-byte flash image; five validator tests passed |
| Actual hardware | **PASS** — 100 corpus cases × three resets, including shared-secret/rejection agreement with host and malformed-key checks |
| Firmware recovery | **PASS** — complete readback matches saved original SHA-256; board restarted |
| QEMU / UART / hardware entropy integration | **NOT RUN** — results collected through SWD; public test coins supplied to deterministic APIs |

**Hardware measurements:** DWT CYCCNT, nominal HSI16 clock at 16 MHz, `RCC_CFGR=0`, `FLASH_ACR=0` (zero wait states/caches disabled), interrupts disabled. Same 100 distinct inputs repeated three times; 300 measurements per operation, no discarded warm-up. API-boundary/barrier overhead included; random-input generation excluded. Live SWD polling can perturb bus timing.

| Operation | Median cycles | Minimum–maximum |
|---|---:|---:|
| KeyGen_Internal (`keypair_derand`) | 1,444,249.5 | 1,443,217–1,536,251 |
| Encaps_Internal (`enc_derand`) | 1,515,464 | 1,514,433–1,598,018 |
| Decapsulation (`dec`) | 1,874,357.5 | 1,873,341–1,956,975 |

Image size includes harness and test data. Static SRAM is 6,064 bytes; whole-harness stack watermark is 18,132 bytes in every run, within a 32 KiB reservation. No per-operation stack attribution. Sizes: public key 1,184; secret key 2,400; ciphertext 1,088; shared secret 32 bytes.

**Semantics/limits.** Success returns 0. A modified full-length ciphertext returns 0 with deterministic implicit rejection `SHAKE256(z || c, 32)`; this is expected, not a vulnerability. Malformed public-key modulus returns −4; corrupted embedded secret-key hash returns −5. Wrong-sized buffers violate this fixed-size API's preconditions and were not passed. This is not FIPS certification, an attack, key extraction, or evidence of side-channel resistance. Power/EM leakage needs a separate physical acquisition setup; ordinary cycle profiling cannot establish resistance.

**Follow-up:** reproduce the host checks using [the command guide](validation/README.md) and pinned evidence; a deployment-oriented follow-up would require an audited board entropy provider before testing the randomized APIs. Hardware was validated for this test configuration. [Measurement summary](validation/evidence/hardware-summary.json), [restoration](validation/evidence/restoration.json), and [actual command ledger](validation/COMMANDS.md) are retained in the repository. At the end of the original experimental session, work was uncommitted on `validation/mlkem-host-board` and nothing had been pushed. At the later review, the checkout contained commit `096f096` and an `origin` remote for `joeywwong/ml-kem-m4`; that later state does not change the historical execution record.
