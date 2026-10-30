# Executed commands and final statuses

**Redacted public copy.** Local user/workspace/installation prefixes use
descriptive placeholders. The unmodified ledger is retained privately.
See [publication notes](PUBLICATION.md) and the
[evidence redaction manifest](evidence/redaction-manifest.json).

Historical ledger of the original experimental session, not a reproduction checklist. Working directory: `<repo>`, unless explicitly noted. The instruction document was read before work; its GF(2) milestone condition and temporary board flashing/restoration were explicitly confirmed by the user. No commit or push command was run during that session. Hardware commands below can overwrite firmware or reset the device; use [the host-only guide](README.md) for safe reproduction.

**Later repository state:** review began at commit `096f096` on `validation/mlkem-host-board`, with `origin` configured for `https://github.com/joeywwong/ml-kem-m4.git`. The commands and statuses below retain their original time scope. The later review is recorded separately in [REVIEW.md](REVIEW.md).

## Setup and inspection actually performed

The initial folder contained only `docs/` and was not a Git repository. These are the relevant setup/discovery commands, including failed attempts. Private instruction paths and commands that disclose them are omitted.

```powershell
Get-Location
rg --files -g AGENTS.md -g '*.md' -g '!vendor' -g '!node_modules'
git status --short
Get-ChildItem -Force
Get-ChildItem -Path <user-home> -Filter AGENTS.md -Force
Get-ChildItem -Path <users> -Filter AGENTS.md -Force
Get-ChildItem -Path C:/ -Filter AGENTS.md -Force
Get-Command git,gcc,clang,cmake,ninja,make,arm-none-eabi-gcc,openocd,STM32_Programmer_CLI,python,python3,wsl -ErrorAction SilentlyContinue | Select-Object Name,Source
Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Name
Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match 'STM32|ST-Link|STLink|J-Link|USB.Serial|CH340|CP210' } | Select-Object Status,FriendlyName,InstanceId
git init -b validation/mlkem-host-board
New-Item -ItemType Directory -Force validation,validation/evidence,validation/scripts,validation/upstream | Out-Null
gcc --version
cmake --version
ninja --version
wsl --list --quiet
[System.IO.Ports.SerialPort]::GetPortNames()
Get-ChildItem -Path <stm32-tools>,<msys2>,<chocolatey>/bin,<user-home>/.platformio/packages -ErrorAction SilentlyContinue | Select-Object FullName
git clone --depth 1 https://github.com/pq-code-package/mlkem-native.git validation/upstream/mlkem-native
rg --files <stm32-tools>/STM32CubeIDE_2.2.0 -g '*arm-none-eabi-gcc.exe' -g '*STM32_Programmer_CLI.exe' -g '*openocd.exe' -g '*make.exe' -g '*qemu*'
Get-ItemProperty -Path HKLM:/HARDWARE/DEVICEMAP/SERIALCOMM -ErrorAction SilentlyContinue
git clone --depth 1 https://github.com/mupq/pqm4.git validation/upstream/pqm4
git ls-remote https://github.com/usnistgov/ACVP-Server.git refs/tags/v1.1.0.43 'refs/tags/v1.1.0.43^{}'
```

Upstream README/build/API/test source, pqm4 target and linker files were inspected with `Get-Content`, `rg` and `git rev-parse HEAD`; pinned identities are in `provenance.json`. Official GitHub, NIST and ST pages were also read. No upstream cryptographic source was edited.

Installed tool discovery and initial device reads used:

```powershell
$armCompiler = (Get-ChildItem '<stm32-tools>/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/*/tools/bin/arm-none-eabi-gcc.exe').FullName
& $armCompiler --version
$programmer = (Get-ChildItem '<stm32-tools>/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/*/tools/bin/STM32_Programmer_CLI.exe').FullName
& $programmer --list
& $programmer -c port=SWD mode=HOTPLUG -r32 0xE0042000 4 -r16 0x1FFF7A22 2
& $programmer -c port=SWD mode=HOTPLUG -u 0x08000000 1048576 validation/build/original-flash.bin
Add-Content .git/info/exclude '/validation/backups/'
& $programmer -c port=SWD mode=HOTPLUG -u 0x08000000 1048576 validation/backups/original-flash.bin
Get-FileHash validation/backups/original-flash.bin -Algorithm SHA256
```

The first backup destination did not exist and that command failed to save. The second destination was created before retrying; its complete backup was later independently verified against a fresh board read. Programmer output sometimes exits zero despite errors, so the runner also checks its output and downloaded file contents.

## Build, validation and hardware commands actually run

```powershell
python validation/scripts/run_host.py
python validation/scripts/build_board.py
```

The initial ACVP run was executed from `validation/upstream/mlkem-native`:

```powershell
python test/acvp/acvp_client.py --version v1.1.0.43 --jobs 4 > ../../evidence/acvp.txt 2>&1
```

Then, from the project root:

```powershell
python validation/scripts/run_board.py --execute
python validation/scripts/fetch_upstream.py
python validation/scripts/run_acvp.py
python validation/scripts/test_elf_validation.py 2>&1 | Tee-Object validation/evidence/elf-validator-tests.txt
python validation/scripts/run_host.py
```

Some commands were repeated after the resolved failures below. **Exact expanded compiler/linker/test/programmer argument arrays and working directories for each scripted attempt are retained in [evidence/commands.jsonl](evidence/commands.jsonl).** This includes every hardware upload, reset, flash, verify and restoration operation. It is an executed-command ledger, not a suggested command list. The restore SHA-256 is recorded in `evidence/restoration.json`.

| Check | Final status |
|---|---|
| Host functional 512/768/1024, default 1,000 iterations each | PASS |
| Host 100-case corpus and independent implicit-rejection formula | PASS |
| Official NIST ACVP, 435 cases with immutable vector hashes | PASS |
| ARM compilation, ELF segments, exact binary/ELF byte correspondence | PASS |
| ELF validator: five positive/negative checks | PASS |
| Hardware ML-KEM-768, 100 cases × three resets | PASS |
| Original 1 MiB firmware restoration, hash verification and restart | PASS |
| QEMU, UART capture, hardware entropy/randomized API benchmark | NOT RUN |
| Attacks, extraction, power/EM measurements, side-channel security analysis | NOT RUN; outside scope |
| Project commits / GitHub push during the original experimental session | NOT RUN |

Resolved intermediate FAIL statuses: initial `git status` found no repository; sandbox access blocked the first exclude-file edit, Git download, WSL/CIM enumeration and ARM compiler launch. Required local Git/network/tool/device operations were retried with permitted access; WSL/CIM were unnecessary. The first backup failed to save to a missing directory. The first ARM build caught an uninitialized diagnostic-array warning, fixed without touching upstream code. The first authorized hardware-run attempt stopped before programming because the binary check incorrectly selected an ARM_EXIDX header; it was corrected to select the file-backed PT_LOAD header. Automatic review initially rejected flashing; the user then explicitly approved temporary flashing and restoration. Subsequent compilation, guards, hardware tests and recovery passed. No cryptographic functional test failure was observed.

## Final Git checks in the original experimental session

```powershell
git status --short --ignored
git branch --show-current
git remote -v
git diff --check
git check-ignore -v validation/backups/original-flash.bin
```

At that session's end, the project branch was `validation/mlkem-host-board` (unborn, no commits), with no remote configured. The private instruction file, firmware backups, fetched sources, build outputs and Python cache were locally excluded. No `.gitignore` was created in that session; the later repository review added a version-controlled [`.gitignore`](../.gitignore).
