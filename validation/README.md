# Reproduce the ML-KEM validation

Read [the project overview](../README.md) first; [the original outcome](../MLKEM_BOARD_PROGRESS.md) records the experimental session. This directory contains a small test harness and build/measurement scripts; all cryptography is compiled directly from the pinned, unmodified mlkem-native source. The upstream monolithic compilation unit is its documented build method. Upstream license terms remain in the fetched repositories (the mlkem-native library offers Apache-2.0 OR ISC OR MIT; auxiliary files have separate terms). See [licensing and attribution](REVIEW.md#licensing-and-attribution).

## Safe host-only reproduction

Use Python 3, Git and host GCC on `PATH`; ARM GCC/newlib is needed only for cross-compilation. The recorded machine used Python 3.13, MinGW GCC 13.2.0 and STM32CubeIDE's bundled ARM GCC 14.3.1/CubeProgrammer 2.23.0. Scripts use only Python's standard library. Run from the repository root; do not use `python -O`. Existing upstream checkouts must match the pins and have no tracked modifications. Windows/PowerShell is the verified environment; other platforms are not verified.

Set both output overrides before running scripts to preserve the committed experiment and original build. Use a fresh output directory for each retained rerun; stop on any nonzero exit code. The first fetch requires network access if dependencies are absent; subsequent checks use local sources/vectors.

```powershell
$env:MLKEM_BUILD_DIR = 'validation/build/reproduce/build'
$env:MLKEM_EVIDENCE_DIR = 'validation/build/reproduce/evidence'
New-Item -ItemType Directory -Force $env:MLKEM_EVIDENCE_DIR | Out-Null
python validation/scripts/fetch_upstream.py
python validation/scripts/run_host.py
python validation/scripts/run_acvp.py
```

Optional offline cross-compilation and ELF tests (no programmer or board access):

```powershell
python validation/scripts/build_board.py
python validation/scripts/test_elf_validation.py
```

The default ARM tool lookup targets this machine's `<stm32-tools>/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins`. On another installation pass the compiler explicitly:

```powershell
python validation/scripts/build_board.py 'C:/your/toolchain/bin/arm-none-eabi-gcc.exe'
```

`fetch_upstream.py` fetches exact Git commits and NIST vector files by commit with SHA-256 verification. It never resets an existing checkout. The version-controlled [`.gitignore`](../.gitignore) excludes fetched dependencies, build outputs, backups, Python caches and the local instruction document; the fetch script also retains its original redundant `.git/info/exclude` setup. There is no committed instruction document. Ignore rules do not remove already tracked files or prevent `git add -f`.

`run_host.py` builds the unmodified upstream functional and ACVP executables for 512/768/1024. Each upstream functional suite uses its default 1,000 iterations and test-only RNG. The additional 768 corpus uses the persisted 9,600 bytes in `evidence/test-coins.bin`: 100 independent 64-byte keygen inputs and 32-byte encapsulation inputs originally generated with `os.urandom`. A fresh output directory receives a copy of those coins; an existing output directory reuses its own coins. These are **public test inputs, never production keys or randomness**. It generates board headers in the selected build directory and checks rejection independently using Python `hashlib.shake_256`. ACVP executables are generated under the ignored upstream checkout's `test/build/`, as expected by its client. The ACVP command runs 75 keygen, 165 encap/decap, and 195 tr1 cases (435 total) against NIST's expected outputs; it is not a certification.

The overrides resolve relative to the repository root and apply to scripts importing `run_host.py`. Without them, scripts retain the original `validation/build/` and `validation/evidence/` defaults and overwrite named outputs. To end the host reproduction session, remove the overrides:

```powershell
Remove-Item Env:MLKEM_BUILD_DIR, Env:MLKEM_EVIDENCE_DIR
```

## Hardware identification and scope

The owner identified the tested board as STM32F407G-DISC1 but earlier reported a possible **VET6** marking. No photograph or definitive physical part identification is committed. ST's [UM1472 board manual](https://www.st.com/resource/en/user_manual/um1472-discovery-kit-with-stm32f407vg-mcu-stmicroelectronics.pdf) specifies VGT6 for the standard kit. ST lists [VE](https://www.st.com/en/microcontrollers-microprocessors/stm32f407ve.html) with 512 KiB flash; the standard VG kit has 1 MiB. The discrepancy remains unresolved.

Direct recorded observations are in [board-identification.txt](evidence/board-identification.txt): device ID `0x413` (a family identifier, not a flash-size variant), debugger register `0xE0042000 = 0x0009A413`, and flash-size register `0x1FFF7A22 = 0x0400` (1,024 KiB). The [run records](evidence/hardware-run-1.json) also contain Cortex-M4 CPUID `0x410fc241`. The [restoration record](evidence/restoration.json) reports a matching 1,048,576-byte readback. These observations support the tested mapping; they do not establish the package marking, board authenticity, or independently addressable capacity of all flash cells.

The [unchanged linker script](src/stm32f407vg.ld) uses 1 MiB flash at `0x08000000` and 128 KiB contiguous main SRAM at `0x20000000`, with a 32 KiB stack reservation; the separate 64 KiB CCM is unused. The recorded flash image occupies only 29,608 bytes, below either nominal flash capacity. No evidence justifies changing the map for this historical build. The filename's `vg` suffix is a build configuration label, not proof of physical identification. All hardware results apply to this tested configuration; resolve the discrepancy before any future programming. This documentation review did not access the device.

## Board execution and recovery

**Historical hardware procedure, separate from host reproduction.** The completed run used ST-Link over SWD. The runner requires the recorded family ID and 1 MiB register reading, but cannot verify the physical marking or establish board suitability by itself. The commands below write flash and/or reset the device. They are not instructions to program an unidentified board.

The local `backups/original-flash.bin` is a complete 1 MiB snapshot and is excluded from Git. Its expected SHA-256 is in `evidence/backup-manifest.json`. The runner first reads flash again and refuses to proceed if it differs from the saved backup. For a different board or changed firmware, make a **new, separate backup** and update that manifest only after independently verifying it. Do not overwrite the existing original backup.

Only after independent board verification, a separately verified backup, explicit approval of temporary firmware replacement, and preparation of matching build/evidence/backup paths, the original runner invocation was:

```powershell
python validation/scripts/run_board.py --execute
```

On another tool installation add `--programmer 'C:/your/tools/STM32_Programmer_CLI.exe'`. This performs the following concrete actions:

1. Read the ID/flash-size register and option bytes; verify the backup's size/hash and a fresh full flash readback.
2. Check every ELF PT_LOAD virtual range and flash load range, entry point, and exact binary bytes. Main SRAM includes a 32 KiB reserved stack; the linker rejects static-data overlap. Offline tests exercise flash overflow, RAM overflow, wrong architecture and the valid image.
3. Program/verify the test binary at `0x08000000`; reset the target.
4. Run the same 100 cases three times, resetting between repetitions. Read the 1,264-byte result block at `0x20000000` every five seconds via hot-plug SWD. Accept only a completed success record, correct sample count and nonzero cycle values. Save raw binary, decoded JSON, and programmer logs.
5. In a `finally` block, restore the full original flash, verify programming, read back all 1 MiB, compare SHA-256, then restart the original firmware. A process kill, power/USB failure or disconnected debugger can still interrupt recovery; the backup remains local for manual recovery.

The actual run restored SHA-256 `b2f05184ed6327f11f53da240ea76247746bc0f12221df5f416a33e1bc0b72c6`. Recovery commands actually used, with `$programmer` set to the installed executable, were:

```powershell
& $programmer -c port=SWD mode=UR -w '<repo>/validation/backups/original-flash.bin' 0x08000000 -v
& $programmer -c port=SWD mode=HOTPLUG -u 0x08000000 1048576 '<repo>/validation/backups/restored-readback.bin'
& $programmer -c port=SWD mode=HOTPLUG -rst
```

## Measurement interpretation

`src/startup.S` sets up data/BSS and paints the entire reserved stack with `0xA5A5A5A5` before entering C. `src/validation.c` uses only mlkem-native public APIs. The reset clock tree is checked before timing: HSI16, AHB /1, PLL off, zero flash wait states. `RCC_CR=0x6983`, `RCC_CFGR=0`, `FLASH_ACR=0`, `DWT_CTRL=0x40000001` were read back. The 16 MHz clock is nominal/configured, not measured with an external frequency instrument. No UART pins or baud rate were assumed; **UART output was NOT RUN**. Results came from a documented RAM block through SWD. pqm4's ordinary UART wiring is USART2 PA2 TX/PA3 RX, typically 38400 baud; this harness does not initialize it.

DWT CYCCNT surrounds each deterministic keygen/encapsulation call and decapsulation. Counts include call-boundary/barrier overhead, exclude entropy generation and setup, and include the upstream API's zeroization. Interrupts are disabled; no warm-up samples are discarded. SWD reads can perturb bus timing, so the recorded range is part of the result. There are 100 distinct inputs, repeated on three resets, not 300 independent inputs. No emulator timing or upstream published measurements are presented as local hardware data.

Stack use is a whole-harness high-water measurement rounded to words; it includes nested crypto calls and validation code, while the keys/ciphertext and results occupy static SRAM. A watermark is an estimate and cannot prove absence of every possible stack overflow. Reported image size includes startup, test coins, expected secrets and the harness, not just library code. Keygen/encapsulation use public deterministic APIs; hardware entropy integration and the randomized API's end-to-end latency are NOT RUN.

An altered fixed-size ciphertext returns success and an implicit-rejection secret. Repeating it produces the same secret; on host this is checked against `SHAKE256(z || c, 32)`, and on hardware it is compared to the recorded host result. Invalid public-key coefficients return `MLK_ERR_INVALID_PK` (−4); a corrupted embedded public-key hash returns `MLK_ERR_INVALID_SK` (−5). Other documented errors include RNG failure (−3), allocation failure (−2), and optional pairwise consistency failure (−6); this deterministic/default-allocation configuration does not exercise them. Truncated/null/overlapping buffers violate the upstream API contract and are not used.

No attack, extraction, side-channel analysis or countermeasure was attempted. Power/EM work requires separate physical instrumentation; these functional tests and cycle measurements do not establish side-channel resistance. The normative scheme is [NIST FIPS 203](https://csrc.nist.gov/pubs/fips/203/final).

## Evidence and commands

[`evidence/hardware-summary.json`](evidence/hardware-summary.json) contains medians/ranges, image hashes and stack measurements. The three [run 1](evidence/hardware-run-1.json), [run 2](evidence/hardware-run-2.json) and [run 3](evidence/hardware-run-3.json) files contain all 900 cycle values. Corresponding `.bin` files are **redacted public copies**, with only offsets 56–63 zeroed; logs replace local paths and probe serials with placeholders. Every original/public evidence hash and transformation is listed in the [redaction manifest](evidence/redaction-manifest.json). Unmodified originals remain private. [`restoration.json`](evidence/restoration.json) records the full-flash recovery check. [`provenance.json`](provenance.json) fixes source and vector identities. Preserve the public evidence and use output overrides for fresh checks.

[`source-hashes.json`](evidence/source-hashes.json) still describes the original session's scripts and firmware source. Later changes route output in `run_host.py` and initialize the two reserved words in `src/validation.c`. Those current sources are not the exact historical firmware source. The recorded firmware hashes, sizes and hardware measurements remain historical; a new build has its own image identity and requires separate evidence. See [publication notes](PUBLICATION.md).

[COMMANDS.md](COMMANDS.md) lists the original session's executed top-level commands and setup observations. [evidence/commands.jsonl](evidence/commands.jsonl) records expanded process argument arrays and working directories, including compilers, ACVP, device reads, flashing and restoration, with local path prefixes redacted. Setup failures and the pre-flash guard correction are disclosed in the command guide. No commands committed or pushed project work during that original session; the repository was subsequently committed and an origin remote configured. The later review is in [REVIEW.md](REVIEW.md).
