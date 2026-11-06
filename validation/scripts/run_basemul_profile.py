"""Gated ST-LINK cycle collection with immutable backup and verified restoration.

Private programmer logs/backups stay under ignored validation/backups/. Public
RAM reports contain only test metadata and cycle counts, not secret buffers.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time

from run_host import ROOT, VAL, UP, PIN
from build_board import validate_elf
from prepare_basemul_profile import REPORT_WORDS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_firmware(directory, mode_summary):
    elf = directory / 'profile.elf'
    if validate_elf(elf, 512) != mode_summary['elf']:
        raise RuntimeError('ELF differs from checked build')
    binary = directory / 'profile.bin'
    if sha(binary) != mode_summary['firmware_sha256']:
        raise RuntimeError('Firmware hash differs from checked build')
    data = elf.read_bytes()
    phoff = struct.unpack_from('<I', data, 28)[0]
    phsize, phcount = struct.unpack_from('<HH', data, 42)
    segments = [struct.unpack_from('<8I', data, phoff + i * phsize) for i in range(phcount)]
    segments = [p for p in segments if p[0] == 1 and p[4]]
    if len(segments) != 1 or segments[0][3] != 0x08000000:
        raise RuntimeError('Expected exactly one file-backed flash segment')
    p = segments[0]
    if binary.read_bytes() != data[p[1]:p[1]+p[4]]:
        raise RuntimeError('Binary is not the exact checked ELF flash segment')


def decode(data, mode):
    if len(data) != REPORT_WORDS * 4:
        raise RuntimeError('Wrong report byte count')
    w = struct.unpack('<' + str(REPORT_WORDS) + 'I', data)
    if w[0] != 0x4D4C4250 or w[1] != 2:
        raise RuntimeError('Wrong result magic/version (possibly stale RAM)')
    if w[2] == 3:
        raise RuntimeError(f'Firmware failure {w[4]}, completed {w[3]}')
    if w[2] != 2:
        return None
    enabled = int(mode == 'instrumented')
    expected = {3: 100, 4: 0, 5: 768, 6: 100, 11: 0x410FC241,
                13: 16000000, 14: enabled, 15: 1, 16: 6, 17: 64,
                18: enabled * 300, 19: enabled * 300}
    for index, value in expected.items():
        if w[index] != value:
            raise RuntimeError(f'Unexpected header word {index}: {w[index]} != {value}')
    if not 0 < w[7] < 32768 or w[9] != 0 or w[10] != 0 or not w[12] & 1:
        raise RuntimeError('Stack, clock, cache or DWT state mismatch')
    if any(w[20:32]):
        raise RuntimeError('Uninitialized reserved report bytes')
    rows = [list(w[32+i*6:38+i*6]) for i in range(100)]
    for row in rows:
        if not all(0 < n < 100_000_000 for n in row[:3]):
            raise RuntimeError('Invalid API cycle count')
        if row[4:] != [enabled, enabled * 3]:
            raise RuntimeError('Hook count mismatch: valid and rejection paths mixed')
        if enabled and not 0 < row[3] < row[2]:
            raise RuntimeError('Invalid basemul cycle count')
        if not enabled and row[3] != 0:
            raise RuntimeError('Uninstrumented baseline contains a region count')
    overhead = list(w[632:696])
    if not all(0 < n < 10000 for n in overhead):
        raise RuntimeError('Invalid empty-bracket measurement')
    return {'status': 'PASS', 'mode': mode, 'samples': 100,
            'report_version': 2, 'completed': w[3], 'failure': w[4],
            'stack_high_water_bytes': w[7], 'rcc_cr': hex(w[8]), 'rcc_cfgr': hex(w[9]),
            'flash_acr': hex(w[10]), 'cpuid': hex(w[11]), 'dwt_ctrl': hex(w[12]),
            'configured_clock_hz': w[13], 'interrupts_disabled': w[15] == 1,
            'expected_total_probe_calls': w[18], 'total_probe_calls': w[19],
            'cycles': rows, 'empty_bracket_cycles': overhead}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True, type=Path)
    parser.add_argument('--private', required=True, type=Path)
    parser.add_argument('--out', type=Path, help='New public result directory, required with --execute')
    parser.add_argument('--execute', action='store_true', help='Explicitly authorize temporary programming and resets')
    parser.add_argument('--programmer', type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    private = args.private.resolve()
    private.mkdir(parents=True, exist_ok=False)
    if args.execute and args.out is None:
        raise RuntimeError('--execute requires --out')
    public = args.out.resolve() if args.out else None
    if public:
        public.mkdir(parents=True, exist_ok=False)
    cli = args.programmer or next(Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins').glob('*/tools/bin/STM32_Programmer_CLI.exe'))
    sequence = 0
    def command(arguments, label, timeout=120):
        nonlocal sequence
        sequence += 1
        argv = list(map(str, [cli, *arguments]))
        with (private / 'commands.jsonl').open('a') as f:
            f.write(json.dumps({'label': label, 'argv': argv}) + '\n')
        p = subprocess.run(argv, capture_output=True, timeout=timeout)
        data = p.stdout + p.stderr
        (private / f'{sequence:03}-{label}.txt').write_bytes(data)
        output = data.decode(errors='replace')
        if p.returncode or re.search(r'Error:|ST-LINK error|No ST-Link detected', output, re.I):
            raise RuntimeError(f'Programmer failed: {label}; see private log (exit {p.returncode})')
        return output

    connection = ['-c', 'port=SWD', 'mode=HOTPLUG']
    summary = json.loads((build / 'build-summary.json').read_text()) if args.execute else None
    if args.execute:
        if summary['status'] != 'PASS HOST AND BUILD; DEVICE NOT RUN' or summary['upstream'] != PIN:
            raise RuntimeError('Build validation missing')
        for mode in ('baseline', 'instrumented'):
            verify_firmware(build / mode, summary['modes'][mode])
        if subprocess.check_output(['git', '-C', UP, 'rev-parse', 'HEAD']).decode().strip() != PIN:
            raise RuntimeError('Upstream pin changed')
        if subprocess.check_output(['git', '-C', UP, 'status', '--porcelain', '--untracked-files=no']).strip():
            raise RuntimeError('Upstream checkout changed')
    listing = command(['-l', 'st-link'], 'probe-list')
    if len(re.findall(r'ST-Link Probe \d+\s*:', listing)) != 1:
        raise RuntimeError('Require exactly one connected ST-LINK probe')
    ident = command(connection + ['-r16', '0x1FFF7A22', '2'], 'identification')
    if '0x413' not in ident or not re.search(r'0x1FFF7A22\s*:\s*0400', ident, re.I):
        raise RuntimeError('Family/flash-size register differs from recorded VG configuration')
    command(connection + ['-r32', '0xE0042000', '4'], 'debug-id')
    command(connection + ['-ob', 'displ'], 'option-bytes-before')
    option_before = command(connection + ['-r32', '0x40023C14', '4'], 'option-word-before')
    option_match = re.search(r'0x40023C14\s*:\s*([0-9A-Fa-f]{8})', option_before, re.I)
    if not option_match:
        raise RuntimeError('Cannot decode option word before programming')
    option_word = option_match.group(1).lower()
    historic = VAL / 'backups/original-flash.bin'
    manifest = json.loads((VAL / 'evidence/backup-manifest.json').read_text(encoding='utf-8-sig'))
    expected_hash = manifest['SHA256'].lower()
    if historic.stat().st_size != 1048576 or sha(historic) != expected_hash:
        raise RuntimeError('Historical original backup size/hash mismatch')
    backup = private / 'current-flash.bin'
    command(connection + ['-u', '0x08000000', '1048576', backup], 'current-flash-readback')
    if backup.stat().st_size != 1048576 or sha(backup) != expected_hash:
        raise RuntimeError('Current flash differs from historical backup; STOP before programming')
    backup_manifest = {'status': 'PASS', 'bytes': 1048576, 'sha256': expected_hash,
                       'matches_historical_original': True, 'configuration': 'existing VG configuration as requested by owner'}
    (private / 'preflight.json').write_text(json.dumps(backup_manifest, indent=2) + '\n')
    print('PASS: one probe, expected family/flash register, full current flash matches original backup', flush=True)
    if not args.execute:
        print('Read-only preflight complete; no reset or programming requested', flush=True)
        return
    reports = []
    experiment_error = None
    modified = False
    try:
        for mode in ('baseline', 'instrumented'):
            modified = True  # Includes partly failed programming commands.
            command(['-c', 'port=SWD', 'mode=UR', '-w', build / mode / 'profile.bin',
                     '0x08000000', '-v', '-rst'], f'flash-{mode}')
            for repetition in range(1, 4):
                if repetition > 1:
                    # Invalidate completed NOLOAD RAM before reset. A failed
                    # reset must not be mistaken for a fresh successful run.
                    command(connection + ['-w32', '0x20000000', '0x00000000'],
                            f'{mode}-invalidate-{repetition}')
                    command(connection + ['-rst'], f'{mode}-reset-{repetition}')
                deadline = time.monotonic() + 150
                attempt = 0
                while True:
                    # About 51 s nominal at 16 MHz. Avoid live SWD polling during
                    # most computation; still retain possible debugger influence.
                    time.sleep(58 if attempt == 0 else 5)
                    attempt += 1
                    dest = private / f'{mode}-run-{repetition}-poll-{attempt}.bin'
                    command(connection + ['-u', '0x20000000', str(REPORT_WORDS * 4), dest],
                            f'{mode}-run-{repetition}-poll-{attempt}')
                    report = decode(dest.read_bytes(), mode)
                    if report is not None:
                        report['repetition'] = repetition
                        report['raw_sha256'] = sha(dest)
                        report['firmware_sha256'] = summary['modes'][mode]['firmware_sha256']
                        report['acquisition_sequence'] = len(reports) + 1
                        reports.append(report)
                        (public / f'{mode}-run-{repetition}.bin').write_bytes(dest.read_bytes())
                        (public / f'{mode}-run-{repetition}.json').write_text(json.dumps(report, indent=2) + '\n')
                        print(f'PASS: {mode}, reset repetition {repetition}, 100 inputs, {report["total_probe_calls"]} hooks, stack {report["stack_high_water_bytes"]}', flush=True)
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError(f'{mode} run {repetition} did not complete')
    except BaseException as error:
        experiment_error = {'type': type(error).__name__, 'message': str(error)}
        (public / 'experiment-failure.json').write_text(json.dumps(experiment_error, indent=2) + '\n')
        raise
    finally:
        if modified:
            print('Restoring original firmware and verifying complete flash readback', flush=True)
            restoration = {'status': 'FAIL', 'bytes': 1048576, 'expected_sha256': expected_hash,
                           'original_restarted': False}
            try:
                if sha(backup) != expected_hash:
                    raise RuntimeError('Private recovery backup changed')
                command(['-c', 'port=SWD', 'mode=UR', '-w', backup, '0x08000000', '-v'], 'restore-original')
                dest = private / 'restored-flash.bin'
                command(connection + ['-u', '0x08000000', '1048576', dest], 'restore-readback')
                restoration['sha256'] = sha(dest)
                if dest.stat().st_size != 1048576 or sha(dest) != expected_hash:
                    raise RuntimeError('Restored full flash hash mismatch')
                command(connection + ['-rst'], 'restart-original')
                command(connection + ['-ob', 'displ'], 'option-bytes-after')
                option_after = command(connection + ['-r32', '0x40023C14', '4'], 'option-word-after')
                option_match = re.search(r'0x40023C14\s*:\s*([0-9A-Fa-f]{8})', option_after, re.I)
                if not option_match or option_match.group(1).lower() != option_word:
                    raise RuntimeError('Option word differs after restoration')
                restoration['option_word_unchanged'] = True
                restoration.update(status='PASS', original_restarted=True)
                print('PASS: original firmware restored, full 1 MiB hash verified, original restarted', flush=True)
            finally:
                (public / 'restoration.json').write_text(json.dumps(restoration, indent=2) + '\n')
    (public / 'build-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (public / 'acquisition.json').write_text(json.dumps({'status': 'PASS', 'runs': len(reports),
        'unique_inputs': 100, 'repetitions_per_mode': 3, 'run_order': ['baseline'] * 3 + ['instrumented'] * 3,
        'preflight': backup_manifest, 'experiment_error': experiment_error,
        'scope': 'DWT processor cycles; no power/EM waveforms',
        'polling': '58-second first wait after each reset; later polls at 5 seconds if required'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
