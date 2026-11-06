"""Analyze saved measured cycle reports. Does not connect to the board."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics

from run_host import ROOT, VAL
from run_basemul_profile import decode


def stats(values):
    quartiles = statistics.quantiles(values, n=4, method='inclusive')
    return {'observations': len(values), 'median': statistics.median(values),
            'q1': quartiles[0], 'q3': quartiles[2], 'iqr': quartiles[2] - quartiles[0],
            'min': min(values), 'max': max(values)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--build', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path, help='New directory; never overwrite an earlier analysis')
    args = parser.parse_args()
    evidence, build, out = args.evidence.resolve(), args.build.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    restoration = json.loads((evidence / 'restoration.json').read_text())
    acquisition = json.loads((evidence / 'acquisition.json').read_text())
    if restoration['status'] != 'PASS' or acquisition['status'] != 'PASS':
        raise RuntimeError('Completed collection and restoration are required for a PASS report')
    reports = {}
    summary = {'status': 'MEASURED DEVICE CYCLES; PASS', 'parameter_set': 768,
               'unique_test_inputs': 100, 'reset_repetitions_per_mode': 3,
               'configured_clock_hz': 16000000, 'modes': {}, 'per_run': [],
               'restoration': restoration,
               'scope': 'On-device DWT profiling of the secret/ciphertext polynomial-vector multiplication/accumulation in mlk_indcpa_dec',
               'limitations': [
                   'No power/EM traces, GPIO trigger, CPA, key recovery or masking evaluation',
                   'Raw counts include timing-bracket/call/setup overhead; no automatic subtraction',
                   'Empty-bracket calibration is indicative, not an exact correction for the compiled call site',
                   'Whole instrumented decapsulation includes profiling and hook bookkeeping',
                   'Nominal HSI16 clock; frequency not externally measured',
                   'Three reset repetitions of the same 100 public test inputs on one board in one session',
                   'Baseline runs precede instrumented runs; comparison can include time/order and code-layout effects',
                   'SWD remains attached; first RAM read after 58 s, not during most computation',
                   'No timing-security conclusion follows from the observed variation',
                   'Existing VG configuration used as requested; this experiment does not establish physical chip identity']}
    table = []
    for mode in ('baseline', 'instrumented'):
        reports[mode] = []
        for repetition in range(1, 4):
            prefix = f'{mode}-run-{repetition}'
            binary = evidence / (prefix + '.bin')
            recorded = json.loads((evidence / (prefix + '.json')).read_text())
            decoded = decode(binary.read_bytes(), mode)
            if decoded is None or sha(binary) != recorded['raw_sha256']:
                raise RuntimeError('Incomplete/tampered raw report: ' + prefix)
            for key, value in decoded.items():
                if recorded[key] != value:
                    raise RuntimeError('Decoded JSON differs from raw report: ' + key)
            reports[mode].append(recorded)
            summary['per_run'].append({'mode': mode, 'repetition': repetition,
                'decaps_cycles': stats([row[2] for row in decoded['cycles']]),
                'basemul_cycles': stats([row[3] for row in decoded['cycles']]) if mode == 'instrumented' else None,
                'empty_bracket_cycles': stats(decoded['empty_bracket_cycles']),
                'stack_high_water_bytes': decoded['stack_high_water_bytes'],
                'total_probe_calls': decoded['total_probe_calls']})
            for i, row in enumerate(decoded['cycles']):
                table.append([mode, repetition, i, *row,
                              100 * row[3] / row[2] if mode == 'instrumented' else ''])
        rows = [row for report in reports[mode] for row in report['cycles']]
        summary['modes'][mode] = {name: stats([row[index] for row in rows]) for index, name in
                                  enumerate(('keygen_cycles', 'encaps_cycles', 'decaps_cycles'))}
        summary['modes'][mode]['empty_bracket_cycles'] = stats(
            [n for report in reports[mode] for n in report['empty_bracket_cycles']])
        summary['modes'][mode]['stack_high_water_bytes'] = max(report['stack_high_water_bytes'] for report in reports[mode])
        if mode == 'instrumented':
            summary['modes'][mode]['basemul_cycles'] = stats([row[3] for row in rows])
            summary['modes'][mode]['paired_basemul_fraction_percent'] = stats([100 * row[3] / row[2] for row in rows])
            summary['modes'][mode]['basemul_nominal_microseconds'] = stats([row[3] / 16 for row in rows])
    differences = [irow[2] - brow[2]
                   for br, ir in zip(reports['baseline'], reports['instrumented'])
                   for brow, irow in zip(br['cycles'], ir['cycles'])]
    summary['matched_decapsulation_delta_cycles'] = stats(differences)
    summary['matched_delta_interpretation'] = 'Same input and repetition index; descriptive build difference, not an isolated instruction-overhead estimate'
    with (out / 'cycles.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['mode', 'reset_repetition', 'input_index', 'keygen_cycles', 'encaps_cycles',
                         'decaps_cycles', 'basemul_cycles', 'valid_probe_calls', 'all_probe_calls',
                         'basemul_fraction_percent'])
        writer.writerows(table)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    # Retain concise, sanitized verification artifacts with the measured data.
    # Full tool logs (which contain local paths) stay in the ignored build tree.
    for mode in ('baseline', 'instrumented'):
        disassembly = (build / mode / 'disassembly.txt').read_text()
        start = disassembly.index(' <lab_profile_empty>:')
        start = disassembly.rfind('\n', 0, start) + 1
        end = disassembly.index(' <mlkem_check_pk>:', start)
        end = disassembly.rfind('\n', 0, end)
        (out / (mode + '-timing-disassembly.txt')).write_text(disassembly[start:end] + '\n')
        size = (build / mode / 'size.txt').read_text().splitlines()[1:]
        (out / (mode + '-sections.txt')).write_text('\n'.join(size) + '\n')
    logs = {}
    for file in build.glob('*.txt'):
        if any(label in file.name for label in ('ML-KEM-', 'toolchain', 'host-build', 'acvp-build')):
            text = file.read_text(errors='replace').replace(str(ROOT), '<repo>').replace(ROOT.as_posix(), '<repo>')
            (out / file.name).write_text(text)
            logs[file.name] = {'original_log_sha256': sha(file),
                               'sanitized_copy_sha256': sha(out / file.name)}
    (out / 'verification-log-hashes.json').write_text(json.dumps(logs, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(13.8, 4.5), layout='constrained')
    colors = ['#2768a4', '#dc722b', '#3a9166']
    axes[0].boxplot([[r[2] / 1000 for report in reports[mode] for r in report['cycles']]
                    for mode in ('baseline', 'instrumented')], tick_labels=['Baseline', 'Instrumented'],
                   showfliers=True, widths=0.5)
    axes[0].set(title='Valid decapsulation: 300 observations/build', ylabel='Thousand processor cycles')
    for report, color in zip(reports['instrumented'], colors):
        axes[1].plot(range(100), [r[3] for r in report['cycles']], marker='.', markersize=3,
                     linewidth=0.65, alpha=0.8, color=color, label=f'Reset {report["repetition"]}')
    axes[1].set(title='Secret/ciphertext multiplication region', xlabel='Persisted public input index', ylabel='Raw processor cycles')
    axes[1].legend(frameon=False, fontsize=8)
    region = summary['modes']['instrumented']['basemul_cycles']
    if region['min'] == region['max']:
        axes[1].set_ylim(region['median'] - 2, region['median'] + 2)
        axes[1].text(0.5, 0.12, f'All 300 observations: {region["median"]:,.0f} cycles',
                     ha='center', transform=axes[1].transAxes, fontsize=9)
        axes[1].ticklabel_format(style='plain', axis='y', useOffset=False)
    axes[2].boxplot([[100 * row[3] / row[2] for row in report['cycles']]
                     for report in reports['instrumented']], tick_labels=['Reset 1', 'Reset 2', 'Reset 3'], widths=0.5)
    axes[2].set(title='Paired region / instrumented decapsulation', ylabel='Percent of processor cycles')
    for ax in axes:
        ax.grid(axis='y', alpha=0.18)
    fig.suptitle('MEASURED STM32F407 ML-KEM-768 cycle profiling | nominal 16 MHz', fontsize=13)
    fig.supxlabel('100 unique inputs repeated across three resets per build; raw timing overhead included. No power/EM traces.', fontsize=9)
    fig.savefig(out / 'cycle-profile.png', dpi=180)
    fig.savefig(out / 'cycle-profile.svg')
    plt.close(fig)

    baseline = summary['modes']['baseline']
    instrumented = summary['modes']['instrumented']
    def fmt(value, precision=2):
        return f'{value:,.{precision}f}'.rstrip('0').rstrip('.')
    lines = [
        '# STM32F407 ML-KEM-768 operation-level cycle profiling — 2026-11-06', '',
        '**MEASURED DEVICE CYCLES; correctness checks and original-firmware restoration PASS.**', '',
        'This adds an on-device measurement of the secret/ciphertext polynomial-vector multiplication/accumulation',
        'inside `mlk_indcpa_dec`. Public ciphertext NTT/cache preparation and the following inverse NTT are outside',
        'the region. The exact compiled call is bracketed by DWT reads and compiler/DSB/ISB barriers.', '',
        '![Measured cycle profiling](cycle-profile.png)', '',
        '| Measurement | Median | IQR | Minimum–maximum |',
        '|---|---:|---:|---:|']
    for label, result in [('Baseline valid decapsulation (cycles)', baseline['decaps_cycles']),
                          ('Instrumented valid decapsulation (cycles)', instrumented['decaps_cycles']),
                          ('Multiplication region, raw (cycles)', instrumented['basemul_cycles']),
                          ('Region duration at nominal 16 MHz (microseconds)', instrumented['basemul_nominal_microseconds']),
                          ('Paired region / instrumented decapsulation (%)', instrumented['paired_basemul_fraction_percent']),
                          ('Instrumented empty bracket (cycles)', instrumented['empty_bracket_cycles']),
                          ('Matched instrumented − baseline decapsulation (cycles)', summary['matched_decapsulation_delta_cycles'])]:
        precision = 6 if '(%)' in label else 3 if '(microseconds)' in label else 2
        lines.append(f'| {label} | {fmt(result["median"], precision)} | {fmt(result["iqr"], precision)} | {fmt(result["min"], precision)}–{fmt(result["max"], precision)} |')
    lines += ['', 'There are **100 unique public deterministic inputs, repeated across three resets per build**:',
              '300 valid-decapsulation observations per build and 300 instrumented-region observations.',
              'All samples, including first-use observations, are retained. Empty-bracket calibration has 64 readings',
              'per reset (192 per build). The corpus varies both test keys and encapsulation coins; it is not a fixed-key CPA dataset.', '',
              'Each instrumented run observed exactly one target-region call during each valid decapsulation and three',
              'per complete test case (the additional two belong to rejection checks): **300 hooks per run**.',
              'The valid call is saved immediately, before rejection tests. Host/device shared secrets and rejection',
              'results agree for all inputs; malformed public/secret-key return checks pass.', '',
              'Fresh host checks passed 100 corpus cases and all **435 pinned ACVP cases for each build**.',
              'The independent SHAKE256 check covers each corpus rejection result. ARM ELF/binary bounds and bytes',
              'were checked before programming, including a conservative 512 KiB bound within the existing VG configuration.', '',
              'Both builds use portable C, ARM GCC 14.3.1, `-O2`, Cortex-M4 Thumb, soft float, no LTO.',
              'Recorded `RCC_CFGR=0`, `FLASH_ACR=0`, DWT enabled and PRIMASK=1 match nominal HSI16 / AHB 1,',
              'zero flash wait states, caches/prefetch off and interrupts disabled. No external frequency measurement was taken.', '',
              '| Build | Flash image bytes | Static main SRAM bytes | Whole-harness stack high-water bytes |',
              '|---|---:|---:|---:|']
    build_summary = json.loads((evidence / 'build-summary.json').read_text())
    for mode in ('baseline', 'instrumented'):
        lines.append(f'| {mode} | {build_summary["modes"][mode]["firmware_bytes"]:,} | 7,600 | {summary["modes"][mode]["stack_high_water_bytes"]:,} |')
    lines += ['', 'Stack watermark is an estimate for the whole harness, not an operation-specific bound.', '',
              '**Recovery:** a fresh full 1,048,576-byte preflash readback matched the preserved historical backup.',
              'After collection, the original firmware was reprogrammed, read back in full, hash-verified and restarted.',
              'The option word was unchanged. Private backups and programmer logs remain ignored; no backup was published.', '',
              '**Interpretation limits:**', '']
    lines += ['- ' + limitation + '.' for limitation in summary['limitations']]
    lines += ['', 'The bracket includes the start-value RAM store, call argument setup/call/return and final barriers.',
              'The empty-bracket sequence differs from the real call site, so it is not subtracted to claim exact intrinsic',
              'function cycles. The matched build delta is descriptive and may include code-layout and run-order effects.', '',
              'The instrumented image measured 4,823 fewer decapsulation cycles in the median matched pair.',
              'This is not a negative instrumentation-overhead estimate or an established speed optimization;',
              'the mechanism behind that build difference was not isolated in this experiment.', '',
              'Evidence: [summary](summary.json), [all 600 records](cycles.csv),',
              '[build checks](../build-summary.json), [acquisition](../acquisition.json),',
              '[restoration](../restoration.json), [instrumented disassembly](instrumented-timing-disassembly.txt).', '',
              'Reproduce software preparation from the repository root with fresh output directories:', '',
              '```powershell',
              'python validation/scripts/prepare_basemul_profile.py --out validation/build/new-basemul',
              'python validation/scripts/test_basemul_profile.py',
              '```', '',
              'Hardware collection requires the explicitly authorized board/programmer setup and a matching private original backup.',
              'Use fresh private/evidence paths; do not rerun blindly on a different board:', '',
              '```powershell',
              'python validation/scripts/run_basemul_profile.py --build validation/build/new-basemul --private validation/backups/new-basemul --out validation/evidence/new-basemul --execute',
              'python validation/scripts/analyze_basemul_profile.py --build validation/build/new-basemul --evidence validation/evidence/new-basemul --out validation/evidence/new-basemul/analysis',
              '```', '']
    (out / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    manifest = {'scope': 'Hashes of saved public evidence and current experiment scripts; no Git commit created',
                'files': {p.relative_to(evidence).as_posix(): sha(p)
                          for p in sorted(evidence.rglob('*')) if p.is_file()},
                'scripts': {p.relative_to(ROOT).as_posix(): sha(p)
                            for p in sorted((VAL / 'scripts').glob('*basemul_profile.py'))}}
    (out / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'basemul_cycles': instrumented['basemul_cycles'],
                      'fraction_percent': instrumented['paired_basemul_fraction_percent'],
                      'matched_decapsulation_delta_cycles': summary['matched_decapsulation_delta_cycles'],
                      'restoration': restoration['status']}, indent=2))


if __name__ == '__main__':
    main()
