"""Offline failure-path checks. Synthetic records are test fixtures, not measurements."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_basemul_profile as profile


def fixture(mode='instrumented'):
    enabled = int(mode == 'instrumented')
    w = [0] * profile.REPORT_WORDS
    w[:20] = [0x4D4C4250, 2, 2, 100, 0, 768, 100, 18132,
              0x6983, 0, 0, 0x410FC241, 0x40000001, 16000000,
              enabled, 1, 6, 64, enabled * 300, enabled * 300]
    for i in range(100):
        w[32+i*6:38+i*6] = [1400000, 1500000, 1900000, enabled * 10000, enabled, enabled * 3]
    w[632:] = [20] * 64
    return w


def pack(w):
    return struct.pack('<' + str(len(w)) + 'I', *w)


class DecoderTests(unittest.TestCase):
    def test_modes_and_region_identity(self):
        for mode in ('baseline', 'instrumented'):
            result = profile.decode(pack(fixture(mode)), mode)
            self.assertEqual(result['samples'], 100)
            self.assertEqual(result['mode'], mode)

    def test_reject_corruption_mixed_paths_and_wrong_mode(self):
        # Wrong magic/version, failure flag, truncated sample count, live
        # interrupts, overwritten valid-call count, invalid region bounds,
        # uninitialized padding, and wrong image mode must all be rejected.
        for index, value in [(0, 0), (1, 1), (2, 3), (3, 99), (15, 0),
                             (36, 3), (35, 2000000), (20, 123), (14, 0)]:
            with self.subTest(index=index):
                w = fixture()
                w[index] = value
                with self.assertRaises(RuntimeError):
                    profile.decode(pack(w), 'instrumented')
        with self.assertRaises(RuntimeError):
            profile.decode(pack(fixture())[:-4], 'instrumented')

    def test_pending_is_not_pass(self):
        w = fixture()
        w[2] = 1
        self.assertIsNone(profile.decode(pack(w), 'instrumented'))


class RecoveryTests(unittest.TestCase):
    def test_partial_program_failure_attempts_full_restore(self):
        self.simulate_program_failure(corrupt_readback=False)

    def test_restore_hash_failure_is_reported_as_failure(self):
        self.simulate_program_failure(corrupt_readback=True)

    def simulate_program_failure(self, corrupt_readback):
        # No programmer is launched. Simulate a write that partly fails and
        # check that the finally path restores, reads back and restarts.
        with tempfile.TemporaryDirectory(prefix='profile-test-', dir=profile.VAL / 'build') as tmp:
            root = Path(tmp)
            val = root / 'validation'
            (val / 'backups').mkdir(parents=True)
            (val / 'evidence').mkdir()
            backup = b'A' * 1048576
            digest = hashlib.sha256(backup).hexdigest()
            (val / 'backups/original-flash.bin').write_bytes(backup)
            (val / 'evidence/backup-manifest.json').write_text(json.dumps({'SHA256': digest}))
            build = root / 'build'
            build.mkdir()
            (build / 'build-summary.json').write_text(json.dumps({
                'status': 'PASS HOST AND BUILD; DEVICE NOT RUN', 'upstream': profile.PIN,
                'modes': {'baseline': {}, 'instrumented': {}}}))
            private, public = root / 'private', root / 'public'
            calls = []
            def fake_run(argv, **kwargs):
                calls.append(argv)
                text = ''
                if '-l' in argv:
                    text = 'ST-Link Probe 0 :'
                elif '-r16' in argv:
                    text = 'Device ID : 0x413\n0x1FFF7A22 : 0400'
                elif '-r32' in argv and '0x40023C14' in argv:
                    text = '0x40023C14 : 0FFFAAED'
                elif '-u' in argv:
                    is_restoration = Path(argv[-1]).name == 'restored-flash.bin'
                    Path(argv[-1]).write_bytes(b'B' * len(backup) if corrupt_readback and is_restoration else backup)
                elif '-w' in argv and any('profile.bin' in arg for arg in argv):
                    return subprocess.CompletedProcess(argv, 1, b'Error: partial program', b'')
                return subprocess.CompletedProcess(argv, 0, text.encode(), b'')
            argv = ['run', '--build', str(build), '--private', str(private), '--out', str(public),
                    '--execute', '--programmer', 'fake-programmer']
            with patch.object(profile, 'VAL', val), patch.object(profile, 'verify_firmware'), \
                 patch.object(sys, 'argv', argv), patch.object(profile.subprocess, 'run', side_effect=fake_run), \
                 patch.object(profile.subprocess, 'check_output', side_effect=[profile.PIN.encode(), b'']):
                expected_error = 'Restored full flash hash mismatch' if corrupt_readback else 'flash-baseline'
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    profile.main()
            restored = json.loads((public / 'restoration.json').read_text())
            self.assertEqual(restored['status'], 'FAIL' if corrupt_readback else 'PASS')
            self.assertEqual(restored['original_restarted'], not corrupt_readback)
            if not corrupt_readback:
                self.assertEqual(restored['sha256'], digest)
            writes = [argv for argv in calls if '-w' in argv]
            self.assertEqual(len(writes), 2)
            self.assertTrue(any('current-flash.bin' in arg for arg in writes[-1]))
            self.assertEqual((val / 'backups/original-flash.bin').read_bytes(), backup)


if __name__ == '__main__':
    unittest.main(verbosity=2)
