"""Verify public evidence and export an explicit allowlist without Git history.

No device access. No commits, pushes, history rewriting or deletion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def publication_files(root):
    """Keep private, generated and unexpected files outside the export."""
    files = ['.gitignore', '.gitattributes', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
             'README.md', 'MLKEM_BOARD_PROGRESS.md', 'validation/README.md',
             'validation/COMMANDS.md', 'validation/REVIEW.md',
             'validation/PUBLICATION.md', 'validation/provenance.json',
             'validation/evidence/README.md',
             'validation/evidence/redaction-manifest.json']
    manifest = json.loads((root / files[-1]).read_text(encoding='utf-8'))
    for item in manifest['files']:
        name = item['path']
        require(re.fullmatch(r'validation/evidence/[A-Za-z0-9_.-]+', name),
                'Unexpected manifest path')
        files.append(name)
    files.extend(p.relative_to(root).as_posix()
                 for p in (root / 'validation/scripts').glob('*.py'))
    files.extend('validation/src/' + name
                 for name in ('validation.c', 'startup.S', 'stm32f407vg.ld'))
    require(len(files) == len(set(files)), 'Duplicate publication path')
    return sorted(files)


def verify(root, originals=None):
    files = publication_files(root)
    evidence = root / 'validation/evidence'
    manifest = json.loads((evidence / 'redaction-manifest.json').read_text())
    for item in manifest['files']:
        data = (root / item['path']).read_bytes()
        require(digest(data) == item['public_sha256'],
                f"Public hash mismatch: {item['path']}")
        if originals:
            original = (originals / 'files' / item['path']).read_bytes()
            require(digest(original) == item['original_sha256'],
                    f"Original hash mismatch: {item['path']}")
            if item['path'].endswith('.bin'):
                expected = original
                if '/hardware-run-' in item['path']:
                    expected = original[:56] + bytes(8) + original[64:]
                require(data == expected, 'Unexpected binary modification')

    # Inspect the entire export; installation defaults in scripts are generic.
    user_path = re.compile(rb'[A-Za-z]:[\\/]+Users[\\/]+', re.I)
    install_path = re.compile(rb'[A-Za-z]:[\\/]+(?:ST|Python[0-9]+|msys64|ProgramData)[\\/]+', re.I)
    serial = re.compile(rb'ST-LINK SN\s*:\s*([^\r\n]+)')
    for name in files:
        data = (root / name).read_bytes()
        if name.endswith('.bin'):
            continue  # Public coins and the fixed-layout RAM records only.
        require(not user_path.search(data), f'Local user path remains: {name}')
        if not name.startswith('validation/scripts/'):
            require(not install_path.search(data), f'Installation path remains: {name}')
        require(all(value.strip() == b'<probe-1>' for value in serial.findall(data)),
                f'Unredacted probe serial: {name}')
        if name.endswith('.json'):
            json.loads(data.decode('utf-8-sig'))
        elif name.endswith('.jsonl'):
            for line in data.decode('utf-8-sig').splitlines():
                json.loads(line)

    all_rows = []
    stacks = []
    for repetition in range(1, 4):
        data = (evidence / f'hardware-run-{repetition}.bin').read_bytes()
        require(len(data) == 1264 and data[56:64] == bytes(8), 'Invalid RAM mask')
        words = struct.unpack('<316I', data)
        require(words[:7] == (0x4D4C4B45, 1, 2, 100, 0, 768, 100),
                'Unexpected hardware report header')
        report = json.loads((evidence / f'hardware-run-{repetition}.json').read_text())
        rows = [list(words[16+i*3:19+i*3]) for i in range(100)]
        require(report['cycles'] == rows and report['status'] == 'PASS'
                and report['repetition'] == repetition and report['samples'] == words[6]
                and report['stack_high_water_bytes'] == words[7], 'RAM/JSON mismatch')
        for field, index in [('rcc_cr', 8), ('rcc_cfgr', 9), ('flash_acr', 10),
                             ('cpuid', 11), ('dwt_ctrl', 12)]:
            require(int(report[field], 16) == words[index], 'Register mismatch')
        require(report['configured_clock_hz'] == words[13], 'Clock mismatch')
        all_rows.extend(rows)
        stacks.append(words[7])
    summary = json.loads((evidence / 'hardware-summary.json').read_text())
    require(summary['stack_high_water_bytes'] == max(stacks), 'Stack summary mismatch')
    for i, operation in enumerate(('keygen_derand', 'encaps_derand', 'decaps')):
        counts = [row[i] for row in all_rows]
        require(summary['cycles'][operation] == dict(samples=len(counts),
                median=statistics.median(counts), min=min(counts), max=max(counts)),
                'Cycle summary mismatch')
    print(f'PASS: {len(files)} publication files; {len(manifest["files"])} evidence hashes; '
          '900 cycles, registers, stack values, JSON and privacy checks')
    return files


def export(root, target, originals=None):
    files = verify(root, originals)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects a previously reviewed export.
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(root / name, arcname=name)
    with zipfile.ZipFile(target) as archive:
        require(sorted(archive.namelist()) == files, 'Export allowlist mismatch')
        for name in files:
            require(archive.read(name) == (root / name).read_bytes(), 'Export byte mismatch')
    print(f'PASS: history-free archive written and byte-verified ({len(files)} files)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'export'))
    parser.add_argument('--originals', type=Path,
                        help='Optional private snapshot directory containing files/')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'validation/publication-export/ml-kem-m4-public.zip')
    args = parser.parse_args()
    if args.action == 'export':
        export(ROOT, args.output, args.originals)
    else:
        verify(ROOT, args.originals)


if __name__ == '__main__':
    main()
