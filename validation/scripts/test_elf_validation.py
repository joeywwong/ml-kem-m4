"""Offline negative checks for the pre-flash memory-range validator."""
from pathlib import Path
import struct
import tempfile
import unittest
from build_board import validate_elf
from run_host import BUILD


class ElfBoundsTests(unittest.TestCase):
    def setUp(self):
        self.source = (BUILD / 'mlkem768-stm32f407vg.elf').read_bytes()
        self.temp = tempfile.TemporaryDirectory(dir=BUILD)
        self.path = Path(self.temp.name) / 'candidate.elf'
        self.path.write_bytes(self.source)
        phoff = struct.unpack_from('<I', self.source, 28)[0]
        phsize, count = struct.unpack_from('<HH', self.source, 42)
        self.headers = [phoff + i * phsize for i in range(count)
                        if struct.unpack_from('<I', self.source, phoff + i * phsize)[0] == 1]

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_image(self):
        self.assertEqual(validate_elf(self.path, 1024)['status'], 'PASS')

    def test_flash_capacity_too_small(self):
        with self.assertRaises(AssertionError):
            validate_elf(self.path, 16)

    def test_flash_load_address_overflow(self):
        data = bytearray(self.source)
        struct.pack_into('<I', data, self.headers[0] + 12, 0x080FFFF0)
        self.path.write_bytes(data)
        with self.assertRaises(AssertionError):
            validate_elf(self.path, 1024)

    def test_ram_extent_overflow(self):
        data = bytearray(self.source)
        struct.pack_into('<I', data, self.headers[-1] + 20, 0x10000)
        self.path.write_bytes(data)
        with self.assertRaises(AssertionError):
            validate_elf(self.path, 1024)

    def test_wrong_architecture(self):
        data = bytearray(self.source)
        struct.pack_into('<H', data, 18, 62)
        self.path.write_bytes(data)
        with self.assertRaises(AssertionError):
            validate_elf(self.path, 1024)


if __name__ == '__main__':
    unittest.main(verbosity=2)
