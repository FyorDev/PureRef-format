"""Reading image size from encoded bytes."""
import struct
import unittest
import zlib

from pureref import imagesize
from support import FIXTURES


def png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    pixels = (b'\0' + b'\xff\x00\x00' * width) * height
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


class IdentifyTests(unittest.TestCase):
    def test_fixtures(self):
        cases = {'red.png': ('PNG', 64, 32), 'blue.png': ('PNG', 40, 80),
                 'tiny.png': ('PNG', 4, 4), 'alpha.png': ('PNG', 8, 8),
                 'anim.gif': ('GIF', 16, 16), 'red.jpg': ('JPG', 64, 32)}
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(imagesize.identify((FIXTURES / name).read_bytes()),
                                 expected)

    def test_generated_png_sizes(self):
        for width, height in [(1, 1), (7, 13), (1000, 3)]:
            self.assertEqual(imagesize.identify(png(width, height)),
                             ('PNG', width, height))

    def test_bmp(self):
        header = (b'BM' + struct.pack('<IHHI', 122, 0, 0, 122)
                  + struct.pack('<Iii', 40, 30, -20) + bytes(80))
        self.assertEqual(imagesize.identify(header), ('BMP', 30, 20))

    def test_tiff_both_byte_orders(self):
        for order, magic in (('<', b'II*\0'), ('>', b'MM\0*')):
            entries = struct.pack(order + 'H', 2)
            entries += struct.pack(order + 'HHIHH', 256, 3, 1, 12, 0)
            entries += struct.pack(order + 'HHIHH', 257, 3, 1, 34, 0)
            data = magic + struct.pack(order + 'I', 8) + entries
            with self.subTest(order=order):
                self.assertEqual(imagesize.identify(data), ('TIFF', 12, 34))

    def test_webp_lossy(self):
        body = b'VP8 ' + bytes(7) + b'\x9d\x01\x2a' + struct.pack('<HH', 100, 60)
        data = b'RIFF' + struct.pack('<I', len(body) + 4) + b'WEBP' + body
        self.assertEqual(imagesize.identify(data), ('WEBP', 100, 60))

    def test_unknown_and_truncated(self):
        for data in (b'', b'nonsense', b'\x89PNG\r\n\x1a\n'):
            with self.subTest(data=data), self.assertRaises(imagesize.UnknownImage):
                imagesize.identify(data)

    def test_jpeg_without_a_size_marker(self):
        with self.assertRaises(imagesize.UnknownImage):
            imagesize.identify(b'\xff\xd8\xff\xd9')


if __name__ == '__main__':
    unittest.main()
