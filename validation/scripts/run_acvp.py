"""Run the upstream client with commit-pinned, hash-checked NIST vectors."""
import hashlib
import json
import sys
from run_host import VAL, UP, EVIDENCE, run


def main():
    lock = json.loads((VAL / 'provenance.json').read_text())['acvp']
    directory = VAL / 'upstream/acvp'
    for relative, expected in lock['sha256'].items():
        if hashlib.sha256((directory / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Vector hash mismatch: {relative}')
    reports = []
    for group in ('ML-KEM-keyGen-FIPS203', 'ML-KEM-encapDecap-FIPS203', 'ML-KEM-encapDecap-FIPS203-tr1'):
        output = run([sys.executable, UP / 'test/acvp/acvp_client.py',
                      '--prompt', directory / group / 'prompt.json',
                      '--expected', directory / group / 'expectedResults.json', '--jobs', '4'],
                     f'acvp-pinned-{group}.txt', cwd=UP)
        if b'ALL GOOD!' not in output:
            # Upstream status output is on stderr; inspect the combined saved log.
            if 'ALL GOOD!' not in (EVIDENCE / f'acvp-pinned-{group}.txt').read_text():
                raise RuntimeError(f'No success marker for {group}')
        prompt = json.loads((directory / group / 'prompt.json').read_text())
        count = sum(len(g['tests']) for g in prompt['testGroups'])
        reports.append({'group': group, 'cases': count, 'status': 'PASS'})
    (EVIDENCE / 'acvp-summary.json').write_text(json.dumps({'status': 'PASS', 'commit': lock['commit'],
        'groups': reports, 'total_cases': sum(r['cases'] for r in reports)}, indent=2) + '\n')
    print('PASS: all pinned ACVP cases', sum(r['cases'] for r in reports))


if __name__ == '__main__':
    main()
