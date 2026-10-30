"""Execute the validated image, collect SWD results, and restore prior firmware.

Requires --execute. Does not change option bytes. Uses a verified full-flash backup.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct
import time
from build_board import validate_elf
from run_host import VAL, BUILD, EVIDENCE, run


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--programmer', type=Path)
    args = parser.parse_args()
    cli = args.programmer or next(Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins').glob('*/tools/bin/STM32_Programmer_CLI.exe'))
    def command(arguments, name):
        output = run([cli] + arguments, name).decode(errors='replace')
        if 'Error:' in output or 'No ST-Link detected' in output:
            raise RuntimeError(f'Programmer reported an error; see {name}')
        return output
    connection = ['-c', 'port=SWD', 'mode=HOTPLUG']
    ident = command(connection + ['-r16', '0x1FFF7A22', '2'], 'preflash-identification.txt')
    assert '0x413' in ident and '0x1FFF7A22 : 0400' in ident, 'Target must match verified 1 MiB STM32F407 board'
    command(connection + ['-ob', 'displ'], 'option-bytes-before.txt')
    backup = VAL / 'backups/original-flash.bin'
    manifest = json.loads((EVIDENCE / 'backup-manifest.json').read_text(encoding='utf-8-sig'))
    assert backup.stat().st_size == 1048576
    assert sha(backup) == manifest['SHA256'].lower()
    second = VAL / 'backups/preflash-verification.bin'
    command(connection + ['-u', '0x08000000', '1048576', second], 'backup-verification.txt')
    assert sha(second) == sha(backup), 'Flash changed since backup: stop, do not flash'
    validation = validate_elf(BUILD / 'mlkem768-stm32f407vg.elf', 1024)
    recorded = json.loads((EVIDENCE / 'elf-validation.json').read_text())
    assert validation == recorded, 'ELF changed after range validation'
    firmware = BUILD / 'firmware.bin'
    # This image currently has one file-backed flash segment; check exact bytes.
    elf = (BUILD / 'mlkem768-stm32f407vg.elf').read_bytes()
    phoff = struct.unpack_from('<I', elf, 28)[0]
    phsize, phcount = struct.unpack_from('<HH', elf, 42)
    file_segments = [struct.unpack_from('<8I', elf, phoff + i * phsize) for i in range(phcount)]
    file_segments = [p for p in file_segments if p[0] == 1 and p[4] > 0]
    assert len(file_segments) == 1 and file_segments[0][3] == 0x08000000
    offset, size = file_segments[0][1], file_segments[0][4]
    assert firmware.read_bytes() == elf[offset:offset+size]
    print('PASS: device, backup, ELF ranges and binary; programming test image', flush=True)
    reports = []
    modified = False
    try:
        modified = True  # Restore even if the programming command partly fails.
        command(['-c', 'port=SWD', 'mode=UR', '-w', firmware, '0x08000000', '-v', '-rst'], 'flash-test-image.txt')
        for repetition in range(1, 4):
            if repetition > 1:
                command(connection + ['-rst'], f'reset-{repetition}.txt')
            deadline = time.monotonic() + 240
            attempt = 0
            while True:
                time.sleep(5)
                attempt += 1
                dest = EVIDENCE / f'hardware-run-{repetition}.bin'
                command(connection + ['-u', '0x20000000', '1264', dest], f'hardware-poll-{repetition}-{attempt}.txt')
                data = dest.read_bytes()
                assert len(data) == 1264
                words = struct.unpack('<316I', data)
                magic, version, status, completed, failure, level, samples, stack = words[:8]
                if magic == 0x4D4C4B45 and status == 3:
                    raise RuntimeError(f'Firmware failure {failure}, completed {completed}')
                if magic == 0x4D4C4B45 and status == 2:
                    break
                print(f'Hardware repetition {repetition}: completed {completed}/100', flush=True)
                if time.monotonic() > deadline:
                    raise TimeoutError('Firmware did not complete within 240 seconds')
            assert version == 1 and completed == samples == 100 and level == 768 and failure == 0
            assert 0 < stack < 32768, 'Stack watermark hit reservation boundary'
            rows = [list(words[16+i*3:19+i*3]) for i in range(100)]
            assert all(0 < count < 100_000_000 for row in rows for count in row)
            report = {'status': 'PASS', 'repetition': repetition, 'samples': samples,
                      'stack_high_water_bytes': stack, 'rcc_cr': hex(words[8]), 'rcc_cfgr': hex(words[9]),
                      'flash_acr': hex(words[10]), 'cpuid': hex(words[11]), 'dwt_ctrl': hex(words[12]),
                      'configured_clock_hz': words[13], 'cycles': rows}
            reports.append(report)
            (EVIDENCE / f'hardware-run-{repetition}.json').write_text(json.dumps(report, indent=2) + '\n')
            print(f'PASS: repetition {repetition}, 100 cases, stack watermark {stack} bytes', flush=True)
    finally:
        if modified:
            print('Restoring original firmware and verifying full flash readback', flush=True)
            command(['-c', 'port=SWD', 'mode=UR', '-w', backup, '0x08000000', '-v'], 'restore-firmware.txt')
            restored = VAL / 'backups/restored-readback.bin'
            command(connection + ['-u', '0x08000000', '1048576', restored], 'restore-readback.txt')
            assert sha(restored) == sha(backup), 'Original firmware restoration verification failed'
            command(connection + ['-rst'], 'restart-original-firmware.txt')
            (EVIDENCE / 'restoration.json').write_text(json.dumps({'status': 'PASS', 'bytes': 1048576,
                'sha256': sha(restored), 'original_restarted': True}, indent=2) + '\n')
    summary = {'status': 'PASS', 'parameter_set': 768, 'repetitions': 3, 'samples_per_repetition': 100,
               'unique_test_inputs': 100, 'clock_hz': 16000000, 'cycles': {},
               'stack_high_water_bytes': max(r['stack_high_water_bytes'] for r in reports),
               'elf_sha256': recorded['elf_sha256'], 'firmware_bin_sha256': sha(firmware)}
    for i, operation in enumerate(['keygen_derand', 'encaps_derand', 'decaps']):
        counts = [row[i] for report in reports for row in report['cycles']]
        summary['cycles'][operation] = {'samples': len(counts), 'median': statistics.median(counts),
                                        'min': min(counts), 'max': max(counts)}
    (EVIDENCE / 'hardware-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
