"""Module to read ppmdu "PMD2" XML files into the config data model"""
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
import os
from typing import List, Union
from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError

import pkg_resources

from skytemple_files.common.ppmdu_config.data import *
from skytemple_files.common.ppmdu_config.script_data import *


class Pmd2XmlReader:
    def __init__(self, file_names: List[str], game_edition: str):
        """
        Create a parser.
        :param file_names: XML files. these will be merged.
        :param game_edition: Game edition, must be in the format XoX_RE (XoX is game version, RE is 2 letter region code).
        :raises ParseError: On XML parse errors
        :raises OSError: If the file wasn't found
        """
        # First merge the external XML files
        roots = []
        for f in file_names:
            this_file_root = ElementTree.parse(f).getroot()
            for elem in this_file_root:
                if elem.tag == 'External':
                    filepath = os.path.join(os.path.dirname(f), elem.attrib['filepath'])
                    this_file_root = XmlCombiner(
                        [this_file_root, ElementTree.parse(filepath).getroot()]
                    ).combine().getroot()
            roots.append(this_file_root)
        self._root = XmlCombiner(roots).combine().getroot()
        self._game_edition = game_edition
        self._game_version = game_edition.split('_')[0]

    @classmethod
    def load_default(cls, for_version='EoS_EU') -> Pmd2Data:
        """
        Load the default pmd2data.xml, patched with the skytemple.xml and create a Pmd2Data object for the version
        passed.
        """
        res_dir = os.path.join(pkg_resources.resource_filename('skytemple_files', '_resources'), 'ppmdu_config')
        return Pmd2XmlReader([
            os.path.join(res_dir, 'pmd2data.xml'),
            os.path.join(res_dir, 'skytemple.xml')
        ], for_version).parse()

    def parse(self) -> Pmd2Data:
        """
        Create a Pmd2Data object from the XML given.
        """
        game_editions = []
        game_constants = {}
        binaries = []
        string_index_data = None
        script_data = None
        for e in self._root:
            ###########################
            if e.tag == 'GameEditions':
                for e_edition in e:
                    game_editions.append(Pmd2GameEdition(
                        e_edition.attrib['id'],
                        e_edition.attrib['gamecode'],
                        e_edition.attrib['region'],
                        self._xml_int(e_edition.attrib['arm9off14']),
                        e_edition.attrib['defaultlang'],
                        self._xml_bool(e_edition.attrib['issupported'])
                    ))
            ###########################
            elif e.tag == 'GameConstants':
                for e_game in e:
                    if ('version' in e_game.attrib and e_game.attrib['version'] == self._game_version) or \
                       ('version2' in e_game.attrib and e_game.attrib['version2'] == self._game_version) or \
                       ('version3' in e_game.attrib and e_game.attrib['version3'] == self._game_version):
                        for e_value in e_game:
                            game_constants[e_value.attrib['id']] = self._xml_int(e_value.attrib['value'])
            ###########################
            elif e.tag == 'Binaries':
                for e_game in e:
                    if ('id' in e_game.attrib and e_game.attrib['id'] == self._game_edition) or \
                       ('id2' in e_game.attrib and e_game.attrib['id2'] == self._game_edition) or \
                       ('id3' in e_game.attrib and e_game.attrib['id3'] == self._game_edition):
                        for e_binary in e_game:
                            blocks = []
                            for e_block in e_binary:
                                blocks.append(Pmd2BinaryBlock(
                                    e_block.attrib['name'],
                                    self._xml_int(e_block.attrib['beg']),
                                    self._xml_int(e_block.attrib['end'])
                                ))
                            binaries.append(Pmd2Binary(
                                e_binary.attrib['filepath'],
                                self._xml_int(e_binary.attrib['loadaddress']),
                                blocks
                            ))
            ###########################
            elif e.tag == 'StringIndexData':
                for e_game in e:
                    if ('id' in e_game.attrib and e_game.attrib['id'] == self._game_edition) or \
                       ('id2' in e_game.attrib and e_game.attrib['id2'] == self._game_edition) or \
                       ('id3' in e_game.attrib and e_game.attrib['id3'] == self._game_edition):
                        languages = []
                        string_blocks = []
                        for e_sub in e_game:
                            if e_sub.tag == 'Languages':
                                for e_language in e_sub:
                                    languages.append(Pmd2Language(
                                        e_language.attrib['filename'],
                                        e_language.attrib['name'],
                                        e_language.attrib['locale'],
                                    ))
                            if e_sub.tag == 'StringBlocks':
                                for e_string_block in e_sub:
                                    string_blocks.append(Pmd2StringBlock(
                                        e_string_block.attrib['name'],
                                        self._xml_int(e_string_block.attrib['beg']),
                                        self._xml_int(e_string_block.attrib['end'])
                                    ))
                        string_index_data = Pmd2StringIndexData(
                            languages, string_blocks
                        )
            ###########################
            elif e.tag == 'ScriptData':
                script_data = self._parse_script_data(e)

        return Pmd2Data(
            self._game_edition,
            game_editions,
            game_constants,
            binaries,
            string_index_data,
            script_data
        )

    def _parse_script_data(self, script_root) -> Pmd2ScriptData:
        game_variables_table = []
        objects_list = []
        face_names = []
        face_position_modes = []
        directions = {}
        common_routine_info = []
        menu_ids = []
        process_specials = []
        sprite_effects = []
        level_list = []
        lives_entities = []
        for e_game in script_root:
            if ('id' in e_game.attrib and e_game.attrib['id'] == self._game_edition) or \
               ('id2' in e_game.attrib and e_game.attrib['id2'] == self._game_edition) or \
               ('id3' in e_game.attrib and e_game.attrib['id3'] == self._game_edition):
                for e in e_game:
                    ###########################
                    if e.tag == 'GameVariablesTable' or e.tag == 'GameVariablesTableExtended':
                        for e_var in e:
                            game_variables_table.append(Pmd2ScriptGameVar(
                                e_var.attrib['type'],
                                self._xml_int(e_var.attrib['unk1']),
                                self._xml_int(e_var.attrib['memoffset']),
                                self._xml_int(e_var.attrib['bitshift']),
                                self._xml_int(e_var.attrib['unk3']),
                                self._xml_int(e_var.attrib['unk4']),
                                e_var.attrib['name']
                            ))
                    ###########################
                    elif e.tag == 'ObjectsList':
                        for e_obj in e:
                            objects_list.append(Pmd2ScriptObject(
                                self._xml_int(e_obj.attrib['_id']),
                                self._xml_int(e_obj.attrib['unk1']),
                                self._xml_int(e_obj.attrib['unk2']),
                                self._xml_int(e_obj.attrib['unk3']),
                                e_obj.attrib['name']
                            ))
                    ###########################
                    elif e.tag == 'FaceNames':
                        for e_fn in e:
                            face_names.append(e_fn.text)
                    ###########################
                    elif e.tag == 'FacePositionModes':
                        for e_mode in e:
                            face_position_modes.append(e_mode.text)
                    ###########################
                    elif e.tag == 'Directions':
                        for e_dir in e:
                            directions[self._xml_int(e_dir.attrib['_id'])] = e_dir.text
                    ###########################
                    elif e.tag == 'CommonRoutineInfo':
                        for e_cri in e:
                            common_routine_info.append(Pmd2ScriptRoutine(
                                self._xml_int(e_cri.attrib['id']),
                                self._xml_int(e_cri.attrib['unk1']),
                                e_cri.attrib['name']
                            ))
                    ###########################
                    elif e.tag == 'MenuIds':
                        for e_menu in e:
                            menu_ids.append(Pmd2ScriptMenu(
                                self._xml_int(e_menu.attrib['id']),
                                e_menu.attrib['name']
                            ))
                    ###########################
                    elif e.tag == 'ProcessSpecialIDs':
                        for e_psid in e:
                            process_specials.append(Pmd2ScriptSpecial(
                                self._xml_int(e_psid.attrib['id']),
                                e_psid.attrib['name']
                            ))
                    ###########################
                    elif e.tag == 'SpriteEffectIDs':
                        for e_sei in e:
                            sprite_effects.append(Pmd2ScriptSpriteEffect(
                                self._xml_int(e_sei.attrib['id']),
                                e_sei.attrib['name']
                            ))
                    ###########################
                    elif e.tag == 'LevelList':
                        for e_level in e:
                            level_list.append(Pmd2ScriptLevel(
                                self._xml_int(e_level.attrib['mapid']),
                                e_level.attrib['name'],
                                self._xml_int(e_level.attrib['mapty']) if 'mapty' in e_level.attrib else None,
                                self._xml_int(e_level.attrib['unk2']),
                                self._xml_int(e_level.attrib['unk4'])
                            ))
                    ###########################
                    elif e.tag == 'LivesEntityTable':
                        for e_ent in e:
                            lives_entities.append(Pmd2ScriptEntity(
                                self._xml_int(e_ent.attrib['_id']),
                                self._xml_int(e_ent.attrib['entid']),
                                e_ent.attrib['name'],
                                self._xml_int(e_ent.attrib['type']),
                                self._xml_int(e_ent.attrib['unk3']),
                                self._xml_int(e_ent.attrib['unk4'])
                            ))
        return Pmd2ScriptData(
            game_variables_table,
            objects_list,
            face_names,
            face_position_modes,
            directions,
            common_routine_info,
            menu_ids,
            process_specials,
            sprite_effects,
            level_list,
            lives_entities
        )

    @staticmethod
    def _xml_int(s: str):
        s = s.strip()
        if s.startswith('0x'):
            return int(s, 16)
        return int(s)

    @staticmethod
    def _xml_bool(s: str):
        if s == "false":
            return False
        if s == "true":
            return True
        raise ParseError(f"Invalid boolean '{s}'")


class XmlCombinerMergeConfig:
    def __init__(self, strategy, key):
        self.strategy = strategy
        self.key = key


class XmlCombiner:
    def __init__(self, roots):
        # save all the roots, in order, to be processed later
        self.roots = roots

    def combine(self) -> ElementTree.ElementTree:
        for r in self.roots[1:]:
            # Build MergeConfig
            merge_config = self.read_merge_config(r) or None
            # combine each element with the first one, and update that
            self.combine_element(self.roots[0], r, merge_config)
        # return the string representation
        return ElementTree.ElementTree(self.roots[0])

    def combine_element(self, one, other, merge_config: Union[XmlCombinerMergeConfig, None]):
        """
        This function recursively updates either the text or the children
        of an element if another element is found in `one`, or adds it
        from `other` if not found.
        """
        # Default merge strategy simply works with tag mappings
        one_mapping = {el.tag: el for el in one}
        for el in other:
            if not merge_config:
                # Default merge strategy: Just append, don't change existing attributes.
                # Assume only one per tag exists and map via that.
                try:
                    matching_element_in_one = one_mapping[el.tag]
                except KeyError:
                    # Append
                    one_mapping[el.tag] = el
                    one.append(el)
                    continue
            elif merge_config.strategy == 'key':
                # Key based merge strategy: Map via a field and update all attributes. If no mapping found, append
                matching_element_in_one = self.ms_key__find(one, el, merge_config.key)
                if matching_element_in_one is None:
                    # Append
                    one_mapping[el.tag] = el
                    one.append(el)
                    continue
                else:
                    for key, value in el.attrib.items():
                        matching_element_in_one.attrib[key] = value
            if len(el) > 0:
                # Recursion
                merge_config = self.read_merge_config(el) or None
                self.combine_element(matching_element_in_one, el, merge_config)

    def read_merge_config(self, r):
        if 'merge_strategy' in r.attrib:
            merge_key = r.attrib['merge_key'] if 'merge_key' in r.attrib else None
            return XmlCombinerMergeConfig(r.attrib['merge_strategy'], merge_key)
        return None

    def ms_key__find(self, elem_to_search_in, elem_with_search_field, key):
        search_field = elem_with_search_field.attrib[key]
        for e in elem_to_search_in:
            if key in e.attrib and e.attrib[key] == search_field:
                return e
        return None


if __name__ == '__main__':
    print(Pmd2XmlReader.load_default())
