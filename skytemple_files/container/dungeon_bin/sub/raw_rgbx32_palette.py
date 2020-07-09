#  Copyright 2020 Parakoopa
#
#  This file is part of SkyTemple.
#
#  SkyTemple is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SkyTemple is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SkyTemple.  If not, see <https://www.gnu.org/licenses/>.
from skytemple_files.common.types.data_handler import DataHandler
from skytemple_files.common.util import *


class DbinRawRgbx32PaletteHandler(DataHandler['DbinRawRgbx32Palette']):

    @classmethod
    def deserialize(cls, data: bytes, **kwargs) -> 'DbinRawRgbx32Palette':
        return DbinRawRgbx32Palette(data)

    @classmethod
    def serialize(cls, data: 'DbinRawRgbx32Palette', **kwargs) -> bytes:
        return data.to_bytes()


class DbinRawRgbx32Palette:
    """
    This palette file contains a single raw RGBx palette.
    The model chunks the colors in 16-color palettes.
    The model stores the colors as a stream of RGB values:
    [R, G, B, R, G, B...]
    """
    def __init__(self, data: bytes):
        self.palettes = []
        assert len(data) / 4 % 1 == 0
        pal = []
        for i, (r, g, b, x) in enumerate(iter_bytes(data, 4)):
            pal.append(r)
            pal.append(g)
            pal.append(b)
            assert x == 128  # just in case it isn't... then we'd have a real alpha channel
            if i % 16 == 15:
                self.palettes.append(pal)
                pal = []
        if len(pal) > 0:
            self.palettes.append(pal)

    def to_bytes(self):
        raise NotImplementedError()
