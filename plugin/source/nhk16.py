import os
import json
import sqlite3
from pathlib import Path
from typing import Final

from .audio_source import AudioSource, AudioSourceData
from ..util import get_program_root_path, split_into_mora, katakana_to_hiragana
from ..consts import *

num2fullwidth = str.maketrans("0123456789", "０１２３４５６７８９")

num_map = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十", 11: "十一", 12: "十二", 13: "十三", 14: "十四", 15: "十五", 16: "十六", 17: "十七", 18: "十八", 19: "十九", 20: "二十", 21: "二十一", 22: "二十二", 23: "二十三", 24: "二十四", 25: "二十五", 26: "二十六", 27: "二十七", 28: "二十八", 29: "二十九", 30: "三十", 31: "三十一", 32: "三十二", 33: "三十三", 34: "三十四", 35: "三十五", 36: "三十六", 37: "三十七", 38: "三十八", 39: "三十九", 40: "四十", 41: "四十一", 42: "四十二", 43: "四十三", 44: "四十四", 45: "四十五", 46: "四十六", 47: "四十七", 48: "四十八", 49: "四十九", 50: "五十", 51: "五十一", 52: "五十二", 53: "五十三", 54: "五十四", 55: "五十五", 56: "五十六", 57: "五十七", 58: "五十八", 59: "五十九", 60: "六十", 61: "六十一", 62: "六十二", 63: "六十三", 64: "六十四", 65: "六十五", 66: "六十六", 67: "六十七", 68: "六十八", 69: "六十九", 70: "七十", 71: "七十一", 72: "七十二", 73: "七十三", 74: "七十四", 75: "七十五", 76: "七十六", 77: "七十七", 78: "七十八", 79: "七十九", 80: "八十", 81: "八十一", 82: "八十二", 83: "八十三", 84: "八十四", 85: "八十五", 86: "八十六", 87: "八十七", 88: "八十八", 89: "八十九", 90: "九十", 91: "九十一", 92: "九十二", 93: "九十三", 94: "九十四", 95: "九十五", 96: "九十六", 97: "九十七", 98: "九十八", 99: "九十九", 100: "百", 1000: "千", 10000: "一万"}


def is_kana(word):
    for char in word:
        if char < "ぁ" or char > "ヾ":
            return False
    return True


def get_file_to_relative_path(path):
    file_to_relpath = {}
    for root, _, files in os.walk(path):
        for filename in files:
            file_path = os.path.join(root, filename)
            relpath = os.path.relpath(file_path, path)
            file_to_relpath[filename] = relpath
    return file_to_relpath


def get_numbers(number):
    if number == "何［ナン］":
        return ["何"]
    if int(number) > 100:
        return [num_map[int(number)]]
    else:
        return [f"{number}".translate(num2fullwidth), num_map[int(number)]]


def parse_headwords(headword_list, delimiter):
    kanji_list = []
    for headword in headword_list:
        for x in headword.split(delimiter):
            y = x.strip()
            if y != "":
                kanji_list.append(y)
    return kanji_list



def get_sound_relpath(accent, file_to_relpath):
    sound_file = accent["soundFile"]
    if sound_file is None:
        return None
    if sound_file in file_to_relpath:
        return file_to_relpath[sound_file]
    else:
        return None


def get_display_text(accent):
    display_text_list = []
    pitch_accent_list = []
    prefix = ""
    for word_segment in accent["accent"]:
        pronunciation = word_segment["pronunciation"]
        pitch_offset = 0
        if pronunciation == "（温度":
            continue
        elif pronunciation.startswith("角度）"):
            pronunciation = pronunciation.removeprefix("角度）")
            prefix = "（温度・角度）"
            pitch_offset = -3
        elif pronunciation.startswith("（回数）"):
            pronunciation = pronunciation.removeprefix("（回数）")
            prefix = "（回数）"
            pitch_offset = -4
        mora_list = split_into_mora(pronunciation)
        for silenced_mora in word_segment["silencedMora"]:
            index = silenced_mora - 1
            if len(mora_list) <= index:
                # there are 59 of these invalid(?) entries.
                # seem to be mostly in the numbers section.
                continue

            # This is specifically to differentiate between silenced mora and regular mora,
            # since it's pretty difficult to represent it any other way in Yomichan
            mora_list[index] = katakana_to_hiragana(mora_list[index])

        pitch_accent = int(word_segment["pitchAccent"])
        if pitch_accent + pitch_offset > -1:
            pitch_accent = pitch_accent + pitch_offset
        pitch_accent_list.append(f"{pitch_accent}")
        if pitch_accent > 0:
            mora_list.insert(pitch_accent, "＼")
        display_text_list.append("".join(mora_list))
    display_text = (
        prefix + f"{'・'.join(display_text_list)} [{'・'.join(pitch_accent_list)}]"
    )
    return display_text


def insert_entry(conn, entry):
    cur = conn.cursor()

    sql = 'INSERT INTO entries (expression, reading, source, display, file) VALUES (?,?,?,?,?)'
    cur.execute(sql, entry)

    cur.close()


def add_nhk16_entries(media_dir, conn):
    program_root_path = get_program_root_path()
    media_path = os.path.join(program_root_path, media_dir)
    entries_file = os.path.join(program_root_path, media_dir, "entries.json")
    if not Path(entries_file).is_file():
        print(f"(make_nhk16_table) Cannot find entries file: {entries_file}")
        return

    with open(entries_file, "r", encoding="utf-8", errors="ignore") as f:
        entries = json.load(f)

    file_to_relpath = get_file_to_relative_path(media_path)

    for entry in entries:
        reading = entry["kana"]
        expression_list = parse_headwords(entry["kanji"], "，")

        optional_kanji_list = parse_headwords(entry["kanjiNotUsed"], "，")
        for optional_kanji in optional_kanji_list:
            for expression in expression_list:
                if optional_kanji in expression:
                    expression_list.remove(expression)

        for accent in entry["accents"]:
            sound_file = get_sound_relpath(accent, file_to_relpath)
            if sound_file is None:
                continue
            display_text = get_display_text(accent)
            if len(expression_list) == 0:
                insert_entry(
                    conn, (reading, reading, "nhk16", display_text, sound_file)
                )  # entry
            for expression in expression_list:
                insert_entry(
                    conn, (expression, reading, "nhk16", display_text, sound_file)
                )  # entry

        for subentry in entry["subentries"]:
            if "head" in subentry:
                head_list = parse_headwords([subentry["head"]], "，")
                for accent in subentry["accents"]:
                    sound_file = get_sound_relpath(accent, file_to_relpath)
                    if sound_file is None:
                        continue
                    display_text = get_display_text(accent)
                    for head in head_list:
                        if is_kana(head):
                            insert_entry(
                                conn, (head, head, "nhk16", display_text, sound_file)
                            )  # subentry
                        else:
                            insert_entry(
                                conn, (head, None, "nhk16", display_text, sound_file)
                            )  # subentry
            else:  # number (+counter) section
                expression_list = parse_headwords(entry["kanji"], "・")
                numbers = get_numbers(subentry["number"])
                for accent in subentry["accents"]:
                    sound_file = get_sound_relpath(accent, file_to_relpath)
                    if sound_file is None:
                        continue
                    display_text = get_display_text(accent)
                    if reading == "整数":
                        reading = ""
                    if len(expression_list) == 0:
                        for number in numbers:
                            insert_entry(
                                conn,
                                (
                                    f"{number}{reading}",
                                    None,
                                    "nhk16",
                                    display_text,
                                    sound_file,
                                ),
                            )  # counter
                    for expression in expression_list:
                        for number in numbers:
                            insert_entry(
                                conn,
                                (
                                    f"{number}{expression}",
                                    None,
                                    "nhk16",
                                    display_text,
                                    sound_file,
                                ),
                            )  # counter
    conn.commit()

class NHK16AudioSource(AudioSource):
    def add_entries(self, connection: sqlite3.Connection):
        add_nhk16_entries(self.get_media_dir_path(), connection)

    def get_name(self, row):
        return "NHK16 " + row[DISPLAY]

NHK16_DATA: Final = AudioSourceData("nhk16", "user_files/nhk16_files")
NHK16_AUDIO_SOURCE: Final = NHK16AudioSource(NHK16_DATA)
