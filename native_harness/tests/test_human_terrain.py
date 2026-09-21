import sys
from pathlib import Path
import struct
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from human_play_recorder import terrain_snapshot


class FakeReader:
    def get(self, address, fmt):
        return ((0x8952DCC,0x8952DEC,0x8952E2C,0x8952E4C).index(address)*10000+1000,)

    def read(self, address, length):
        layer = (address-1000)//10000
        offset = (address-1000)%10000//2
        return struct.pack('<'+'H'*(length//2), *[layer*100+i for i in range(offset, offset+length//2)])


class TerrainTests(unittest.TestCase):
    def test_border_and_four_actual_layers(self):
        data = terrain_snapshot(FakeReader(), {'map_size':(10,10), 'pos':(16,16)})
        self.assertEqual(data['origin'], [-4,-4])
        self.assertEqual(len(data['grids']), 4)
        for layer, grid in enumerate(data['grids']):
            self.assertEqual(len(grid),9)
            self.assertTrue(all(len(row)==9 for row in grid))
            self.assertIsNone(grid[0][0])
            self.assertEqual(grid[4][4],layer*100)
            self.assertEqual(grid[8][8],layer*100+44)

    def test_invalid_dimensions(self):
        with self.assertRaises(ValueError):
            terrain_snapshot(FakeReader(), {'map_size':(0,10), 'pos':(16,16)})


if __name__ == '__main__': unittest.main()
