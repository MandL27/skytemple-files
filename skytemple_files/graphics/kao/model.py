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

import math

import warnings

from skytemple_tilequant.image_converter import ImageConverter

try:
    from PIL import Image
except ImportError:
    from pil import Image
from typing import Union, Tuple

from skytemple_files.common.util import *

SUBENTRIES = 40  # Subentries of one 80 byte TOC entry
SUBENTRY_LEN = 4  # Length of the subentry pointers
KAO_IMG_PAL_B_SIZE = 48  # Size of KaoImage palette block in bytes (16*3)
KAO_IMG_PIXEL_DEPTH = 4  # one byte in a kao image are two pixels
KAO_IMG_METAPIXELS_DIM = 8  # How many pixels build a meta-pixel / tile per dim. (8x8)=48
KAO_IMG_IMG_DIM = 5  # How many meta-pixels / tiles build an image per dimension (5x5)=25
KAO_FILE_BYTE_ALIGNMENT = 16  # The size of the kao file has to be divisble by this number of bytes


class KaoImage:
    def __init__(self, whole_kao_data: bytes, start_pnt: int):
        if not isinstance(whole_kao_data, memoryview):
            whole_kao_data = memoryview(whole_kao_data)

        """Construct a KaoImage using a raw image buffer (16 color palette, followed by AT4PX)"""
        from skytemple_files.common.types.file_types import FileType

        cont_len = FileType.AT4PX.cont_size(whole_kao_data, start_pnt + KAO_IMG_PAL_B_SIZE)
        # palette size + at4px container size
        self.original_size = KAO_IMG_PAL_B_SIZE + cont_len
        self.pal_data = read_bytes(whole_kao_data, start_pnt, KAO_IMG_PAL_B_SIZE)
        self.compressed_img_data = read_bytes(whole_kao_data, start_pnt + KAO_IMG_PAL_B_SIZE, cont_len)
        self.as_pil = None  # lazy loading
        self.modified = False

    def get(self) -> Image:
        """Returns the portrait as a PIL image with a 16-bit color palette"""
        if not self.as_pil:
            self.as_pil = kao_to_pil(self)
        return self.as_pil

    def size(self):
        return KAO_IMG_PAL_B_SIZE + len(self.compressed_img_data)

    def get_internal(self) -> bytes:
        """Returns the portrait as 16 color palette followed by AT4PX compressed image data"""
        return bytes(self.pal_data) + bytes(self.compressed_img_data)

    def set(self, pil: Image) -> 'KaoImage':
        """Sets the portrait using a PIL image with 16-bit color palette as input"""
        new_pal, new_img = pil_to_kao(pil)
        self.pal_data = new_pal
        self.compressed_img_data = new_img
        self.modified = True
        self.as_pil = None
        return self

    @classmethod
    def new(cls, pil: Image) -> 'KaoImage':
        """Creates a new KaoImage from a PIL image with 16-bit color palette as input"""
        new_pal, new_img = pil_to_kao(pil)
        new = cls(new_pal + new_img, 0)
        new.modified = True
        return new


class Kao:
    def __init__(self, data: bytes, first_toc: int, toc_len: int):
        if not isinstance(data, memoryview):
            data = memoryview(data)

        self.original_data = data
        self.first_toc = first_toc
        self.toc_len = toc_len
        self.loaded_kaos = [[None for __ in range(0, SUBENTRIES)] for _ in range(0, toc_len)]
        self.loaded_kaos_flat: List[Tuple[int, int, KaoImage]] = []  # cache for performance

    def get(self, index: int, subindex: int) -> Union[KaoImage, None]:
        """Get the KaoImage at the specified location or None if no image is specified"""
        if index >= self.toc_len or index < 0:
            raise ValueError(f"The index requested must be between 0 and {self.toc_len}")
        if subindex >= SUBENTRIES or subindex < 0:
            raise ValueError(f"The subindex requested must be between 0 and {SUBENTRIES}")
        if self.loaded_kaos[index][subindex] is None:
            start_toc_entry = self.first_toc + (index * SUBENTRIES * SUBENTRY_LEN) + subindex * SUBENTRY_LEN
            pnt = read_sintle(self.original_data, start_toc_entry, SUBENTRY_LEN)
            if pnt < 0:
                # NULL pointer
                return None
            self.loaded_kaos[index][subindex] = KaoImage(self.original_data, pnt)
            self.loaded_kaos_flat.append((index, subindex, self.loaded_kaos[index][subindex]))
        return self.loaded_kaos[index][subindex]

    def set(self, index: int, subindex: int, img: KaoImage):
        """
        Set the KaoImage at the specified location. This fails,
        if there is already an image there. Use get instead.
        """
        if index > self.toc_len or index < 0:
            raise ValueError(f"The index requested must be between 0 and {self.toc_len}")
        if subindex > SUBENTRIES or subindex < 0:
            raise ValueError(f"The subindex requested must be between 0 and {SUBENTRIES}")
        if self.get(index, subindex) is not None:
            raise ValueError(f"A kao at this position already exists")

        img.modified = True
        self.loaded_kaos[index][subindex] = img
        self.loaded_kaos_flat.append((index, subindex, self.loaded_kaos[index][subindex]))

    def has_loaded(self, index: int, subindex: int) -> bool:
        """Returns whether or not a kao image at the specified index was loaded"""
        return self.loaded_kaos[index][subindex] is not None

    def __iter__(self) -> 'KaoIterator':
        """
        Iterates over all KaoImages.
        """
        return KaoIterator(self, self.toc_len, SUBENTRIES)


class KaoIterator:
    def __init__(self, kao: Kao, indices: int, subindices: int):
        self.kao = kao
        self.current_index = 0
        self.current_subindex = 0
        self.max_index = indices
        self.max_subindex = subindices

    def __next__(self) -> Tuple[int, int, Union[KaoImage, None]]:
        """Tuple: index, subindex, KaoImage or None"""
        if self.current_index < self.max_index:
            old_index = self.current_index
            old_subindex = self.current_subindex
            ret = None
            try:
                ret = self.kao.get(self.current_index, self.current_subindex)
            except ValueError as ex:
                warnings.warn(f"Could not load KAO at {old_index},{old_subindex}: {ex}")
            self.current_subindex += 1
            if self.current_subindex >= self.max_subindex:
                self.current_index += 1
                self.current_subindex = 0
            return old_index, old_subindex, ret
        else:
            raise StopIteration


def kao_to_pil(kao: KaoImage) -> Image:
    """Converts the data in Kao image to a PIL image"""
    from skytemple_files.common.types.file_types import FileType

    # Generates an array where every three entries a new color begins (r, g, b, r, g, b...)
    uncompressed_image_data = FileType.AT4PX.deserialize(kao.compressed_img_data).decompress()

    return uncompressed_kao_to_pil(kao.pal_data, uncompressed_image_data)


def uncompressed_kao_to_pil(pal_data: bytes, uncompressed_image_data):
    # The images are made up of 25 8x8 tiles stored linearly in the data, but to be arranged
    # as 5x5 "meta-pixels".
    img_dim = KAO_IMG_METAPIXELS_DIM * KAO_IMG_IMG_DIM
    pil_img_data = bytearray(img_dim * img_dim)

    for idx, pix in enumerate(iter_bytes_4bit_le(uncompressed_image_data)):
        # yikes... the mappings below can probably be simplified a lot
        tile_id = math.floor(idx / (KAO_IMG_METAPIXELS_DIM * KAO_IMG_METAPIXELS_DIM))
        tile_x = tile_id % KAO_IMG_IMG_DIM
        tile_y = math.floor(tile_id / KAO_IMG_IMG_DIM)

        idx_in_tile = idx - (KAO_IMG_METAPIXELS_DIM * KAO_IMG_METAPIXELS_DIM) * tile_id
        in_tile_x = idx_in_tile % KAO_IMG_METAPIXELS_DIM
        in_tile_y = math.floor(idx_in_tile / KAO_IMG_METAPIXELS_DIM)

        result_x = tile_x * KAO_IMG_METAPIXELS_DIM + in_tile_x
        result_y = tile_y * KAO_IMG_METAPIXELS_DIM + in_tile_y
        nidx = result_y * img_dim + result_x
        # print(f"{tile_id} : {tile_x}x{tile_y} -- {idx_in_tile} : {in_tile_x}x{in_tile_y} -> {result_x}x{result_y}={nidx}")
        pil_img_data[nidx] = pix

    assert len(pil_img_data) == img_dim * img_dim
    im = Image.frombuffer('P', (img_dim, img_dim), pil_img_data, 'raw', 'P', 0, 1)

    im.putpalette(pal_data)

    return im


def pil_to_kao(pil: Image) -> Tuple[bytes, bytes]:
    """Converts a PIL image (with a 16 bit palette) to a kao palette and at4px compressed image data"""
    from skytemple_files.common.types.file_types import FileType

    img_dim = KAO_IMG_METAPIXELS_DIM * KAO_IMG_IMG_DIM
    if pil.width != img_dim or pil.height != img_dim:
        raise ValueError(f'Can not convert PIL image to Kao: Image dimensions must be {img_dim}x{img_dim}px.')
    if pil.mode != 'P' or pil.palette.mode != 'RGB' or len(pil.palette.palette) != 16 * 3:
        # todo: the transparent color is just some random color, we don't actually want transparency...
        converter = ImageConverter(pil, img_dim, img_dim, (123, 156, 145))
        pil = converter.convert(num_palettes=1, colors_per_palette=16)
    new_palette = bytearray(pil.palette.palette)

    # We have to cut the image back into this annoying tiling format :(
    new_img_size = int(img_dim * img_dim / 2)
    new_img = bytearray(new_img_size)
    raw_pil_image = pil.tobytes('raw', 'P')
    the_two_px_to_write = [0, 0]
    for idx, pix in enumerate(raw_pil_image):
        # We store 2 bytes as one... in LE
        the_two_px_to_write[idx % 2] = pix
        if idx % 2 == 1:
            # -1 because we are always processing 2 px at the same time
            x =( idx-1) % img_dim
            y = int((idx-1) / img_dim)

            tile_x = math.floor(x / KAO_IMG_METAPIXELS_DIM) % KAO_IMG_METAPIXELS_DIM
            tile_y = math.floor(y / KAO_IMG_METAPIXELS_DIM) % KAO_IMG_METAPIXELS_DIM
            tile_id = tile_y * KAO_IMG_IMG_DIM + tile_x

            in_tile_x = x - KAO_IMG_METAPIXELS_DIM * tile_x
            in_tile_y = y - KAO_IMG_METAPIXELS_DIM * tile_y
            idx_in_tile = in_tile_y * KAO_IMG_METAPIXELS_DIM + in_tile_x

            nidx = int((tile_id * KAO_IMG_METAPIXELS_DIM * KAO_IMG_METAPIXELS_DIM + idx_in_tile) / 2)
            #print(f"{idx}@{x}x{y}: {tile_id} : {tile_x}x{tile_y} -- {idx_in_tile} : {in_tile_x}x{in_tile_y} = {nidx}")
            # Little endian:
            new_img[nidx] = the_two_px_to_write[0] + (the_two_px_to_write[1] << 4)

    # You can check if this works correctly, by checking if the reverse action returns the
    # correct image again:
    # >>> uncompressed_kao_to_pil(new_palette, new_img).show()

    new_img_compressed = FileType.AT4PX.serialize(FileType.AT4PX.compress(new_img))

    # You can check if compression works, by uncompressing and checking the image again:
    # >>> unc = FileType.AT4PX.unserialize(new_img_compressed).decompress()
    # >>> uncompressed_kao_to_pil(new_palette, unc).show()

    return new_palette, new_img_compressed
