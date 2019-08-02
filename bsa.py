import functools
import bisect
import os
from abc import ABC
from enum import Enum, IntFlag, auto
from struct import pack
from typing import Set, IO, List

from cached_property import cached_property


class Game(Enum):
    SKYRIM_LE = 0x68
    SKYRIM_SE = 0x69


class ArchiveFlags(IntFlag):
    INCLUDE_DIRECTORY_NAMES = 0x1
    INCLUDE_FILE_NAMES = 0x2
    COMPRESSED_ARCHIVE = 0x4
    RETAIN_FILE_NAMES = 0x10
    XBOX_360 = 0x40
    RETAIN_STRINGS_STARTUP = 0x80
    EMBED_FILE_NAMES = 0x100
    XMEM_CODEC = 0x200
    BETHESDA_DEFAULTS = INCLUDE_DIRECTORY_NAMES | INCLUDE_FILE_NAMES


class FileFlags(IntFlag):
    NONE = 0
    MESHES = 0x1
    TEXTURES = auto()
    MENUS = auto()
    SOUND = auto()
    VOICES = auto()
    SHADERS = auto()
    TREES = auto()
    FONTS = auto()
    MISCELLANEOUS = auto()
    # AUTO = auto()


FILE_FLAGS_EXTENSIONS_MAPPING = {
    ".nif": FileFlags.MESHES,
    ".dds": FileFlags.TEXTURES,
    ".xml": FileFlags.MESHES | FileFlags.MISCELLANEOUS,
    ".wav": FileFlags.VOICES,
    ".fuz": FileFlags.VOICES,
    ".mp3": FileFlags.SOUND,
    ".ogg": FileFlags.SOUND,
    ".txt": FileFlags.SHADERS,
    ".htm": FileFlags.SHADERS,
    ".bat": FileFlags.SHADERS,
    ".scc": FileFlags.SHADERS,
    ".spt": FileFlags.TREES,
    ".fnt": FileFlags.FONTS,
    ".tex": FileFlags.FONTS
}


@functools.total_ordering
class BSAEntry:
    def __init__(self, file_path: str, archive: "BSAArchive"):
        self.file_path = file_path.strip().lower()
        if not self.file_path.startswith(archive.base_dir):
            raise ValueError("The file must be in the base bsa directory")
        self.local_file_path = self.file_path[len(archive.base_dir):].lstrip("\\").strip()

    @property
    def folder_name(self) -> str:
        return "\\".join(self.local_file_path.split("\\")[:-1])

    @property
    def file_name(self) -> str:
        return self.local_file_path.split("\\")[-1]

    @cached_property
    def folder_hash(self) -> int:
        return BSAArchive.tes_hash(self.folder_name)

    @cached_property
    def file_hash(self) -> int:
        return BSAArchive.tes_hash(*self.file_name.split("."))

    def __eq__(self, other: "BSAEntry") -> bool:
        return self.folder_hash == other.folder_hash and self.file_hash == other.file_hash

    def __ne__(self, other: "BSAEntry") -> bool:
        return not (self == other)

    def __lt__(self, other: "BSAEntry") -> bool:
        if self.folder_hash == other.folder_hash:
            return self.file_hash < other.file_hash
        return self.folder_hash < other.folder_hash


class TESHashable(ABC):
    def __init__(self, value: str):
        self.value = value

    @cached_property
    def hash(self) -> int:
        return BSAArchive.tes_hash(self.value)


class BSAFile(TESHashable):
    INVERT_COMPRESS = 0x40000000
    CHUNK_SIZE = 1024 * 1024

    def __init__(self, path: str, offset: int):
        self.path = path
        self.bsa_path = path     # TODO: Fix and check for other memes, we don't want C:\ etc inside BSAs...
        super(BSAFile, self).__init__(self.file_name)
        self.offset = offset

    @property
    def should_compress(self) -> bool:
        return self.size > 32

    @cached_property
    def size(self) -> int:
        return os.path.getsize(self.path)

    def size_with_flag(self, archive_flags: ArchiveFlags):
        r = self.size
        if (archive_flags & ArchiveFlags.COMPRESSED_ARCHIVE) > 0 != self.should_compress:
            r |= BSAFile.INVERT_COMPRESS
        return r

    @property
    def file_name(self) -> str:
        return self.path.split("\\")[-1]

    @cached_property
    def hash(self) -> int:
        return BSAArchive.tes_hash(*self.value.split("."))

    def block(self, archive_flags: ArchiveFlags) -> bytes:
        return pack("<QLL", self.hash, self.size_with_flag(archive_flags), self.offset)

    def _write_uncompressed_data_block(self, out: IO) -> int:
        size = 0
        with open(self.path, "rb") as f:
            while True:
                f_data = f.read(BSAFile.CHUNK_SIZE)
                if not f_data:
                    break
                size += out.write(f_data)
        return size

    def _write_compressed_data_block(self, out: IO) -> int:
        # TODO: https://python-lz4.readthedocs.io/en/stable/quickstart.html#working-with-data-in-chunks
        # with open(self.path, "rb") as f:
        #     while True:
        #         f_data = f.read(BSAFile.CHUNK_SIZE)
        #         if not f_data:
        #             break
        #         out.write(f_data)
        raise NotImplementedError()

    def write_data_block(self, out: IO, archive_flags: ArchiveFlags) -> int:
        if (archive_flags & ArchiveFlags.INCLUDE_FILE_NAMES) > 0:
            out.write(self.bsa_path.encode())
        if self.should_compress and (archive_flags & ArchiveFlags.COMPRESSED_ARCHIVE) > 0:
            return self._write_compressed_data_block(out)
        return self._write_uncompressed_data_block(out)


class BSAString:
    def __init__(self, value: str):
        self.value = value

    def __bytes__(self) -> bytes:
        r = bytearray(pack("<B", len(self.value)))
        r.extend(self.value.encode())
        return bytes(r)


class BSAFolder(TESHashable):
    def __init__(self, name: str, offset: int = 0):
        super(BSAFolder, self).__init__(name)
        self.files: List[BSAFile] = []
        self.offset = offset

    def block(self) -> bytes:
        return pack("<QLLq", self.hash, len(self.files), 0, self.offset)


class BSAArchive:
    def __init__(
        self, base_dir: str,
        game: Game = Game.SKYRIM_SE,
        archive_flags: ArchiveFlags = ArchiveFlags.BETHESDA_DEFAULTS,
        file_flags: FileFlags = FileFlags.NONE,
        share_data: bool = True,
        auto_file_flags: bool = True
    ):
        self.game = game
        self.base_dir = base_dir.strip().lower()
        if not self.base_dir.endswith("\\"):
            self.base_dir += "\\"
        self.archive_flags = archive_flags
        self.auto_file_flags = auto_file_flags
        self.file_flags = file_flags
        self.share_data = share_data
        self.files: Set[str] = set()

        self.folders_count = 0
        self.files_count = 0
        self.folder_names_length = 0
        self.file_names_length = 0

    # def add_files(self, *files: str):
    #     for file_path in files:
    #         file_path = file_path.lower().strip()
    #         for k, v in FILE_FLAGS_EXTENSIONS_MAPPING.items():
    #             if file_path.endswith(k):
    #                 self.file_flags |= v
    #                 break
    #         if os.path.isdir(file_path):
    #         self.files.add(file_path)

    def add_file(self, file_path: str) -> None:
        if "/" in file_path:
            raise ValueError("The file_path must not contain '/'. Please replace it with '\\'.")
        file_path = file_path.lower().strip()
        if not file_path.startswith(self.base_dir):
            raise ValueError("The file must be in the base directory")
        if self.auto_file_flags:
            for k, v in FILE_FLAGS_EXTENSIONS_MAPPING.items():
                if file_path.endswith(k):
                    self.file_flags |= v
                    break
        self.files.add(file_path)

    def add_files(self, *files: str) -> None:
        for file_path in files:
            self.add_file(file_path)

    @staticmethod
    def tes_hash(file_name: str, extension: str = "") -> int:
        print(f"HASH: {file_name} ~ {extension}")
        if extension and not extension.startswith("."):
            extension = f".{extension}"
        chars = [ord(x) for x in file_name]
        hash1 = chars[-1] | (0, chars[-2])[len(chars) > 2] << 8 | len(chars) << 16 | chars[0] << 24
        if extension == ".kf":
            hash1 |= 0x80
        elif extension == ".nif":
            hash1 |= 0x8000
        elif extension == ".dds":
            hash1 |= 0x8080
        elif extension == ".wav":
            hash1 |= 0x80000000
        uint_mask, hash2, hash3 = 0xFFFFFFFF, 0, 0
        for char in chars[1:-2]:
            hash2 = ((hash2 * 0x1003f) + char) & uint_mask
        for char in map(ord, extension):
            hash3 = ((hash3 * 0x1003F) + char) & uint_mask
        hash2 = (hash2 + hash3) & uint_mask
        return (hash2 << 32) + hash1

    def write(self, out: IO) -> None:
        if not self.files:
            raise RuntimeError("No files have been added to the archive.")

        # TODO: Remove this crap
        files: List[BSAEntry] = []
        for file_path in self.files:
            bisect.insort(files, BSAEntry(file_path, self))

        self.folder_names_length = 0
        self.file_names_length = 0

        last_folder_hash = None
        self.folders_count = 0
        self.files_count = 0
        folder_records = []
        # file_records = []
        for file in files:
            if last_folder_hash != file.folder_hash:
                self.folders_count += 1
                last_folder_hash = file.folder_hash
                folder_records.append(BSAFolder(file.folder_name))
                # \x00 terminator => +1
                self.folder_names_length += len(file.folder_name) + 1
            # the 0 (offset) gets filled later
            folder_records[-1].files.append(BSAFile(file.file_path, offset=0))
            # file_records.append(f_record)
            self.files_count += 1
            self.file_names_length += len(file.file_name) + 1

        # Fix flags
        # SSE has no MISCELLANEOUS flag
        self.file_flags &= ~FileFlags.MISCELLANEOUS

        if (self.file_flags & FileFlags.TEXTURES) > 0:
            self.archive_flags |= ArchiveFlags.EMBED_FILE_NAMES
        if (self.file_flags & FileFlags.MESHES) > 0:
            self.archive_flags |= ArchiveFlags.RETAIN_STRINGS_STARTUP
        if (self.file_flags & FileFlags.VOICES) > 0:
            self.archive_flags |= ArchiveFlags.RETAIN_FILE_NAMES

        # These flags below are exclusive for Oblivion
        self.file_flags &= ~(FileFlags.MESHES | FileFlags.FONTS | FileFlags.SHADERS)

        # ALWAYS remove the dummy AUTO flag
        # self.file_flags &= ~FileFlags.AUTO

        # Write header
        offset = 0
        out.seek(offset)
        offset += out.write(bytearray(b"BSA\x00"))
        offset += out.write(
            pack(
                "<llllllll",
                self.game.value,
                36,
                self.archive_flags.value,
                self.folders_count,
                self.files_count,
                self.folder_names_length,
                self.file_names_length,
                self.file_flags.value,
            )
        )

        # Calculate data offset
        # 128 for SSE, 16 for non-SSE
        data_offset = offset + 128 * len(folder_records) + self.file_names_length

        # Write folder records
        for record in folder_records:
            record.offset = data_offset
            data_offset += len(record.value) + 2    # + length prefix + terminator
            data_offset += 16 * len(record.files)
            offset += out.write(record.block())

        # Write file records
        file_records_base = offset
        for folder_record in folder_records:
            offset += out.write(bytes(BSAString(folder_record.value)))
            for file_record in folder_record.files:
                offset += out.write(file_record.block(self.archive_flags))

        # Write file names if necessary
        if (self.archive_flags & ArchiveFlags.INCLUDE_FILE_NAMES) > 0:
            for folder_record in folder_records:
                for file_record in folder_record.files:
                    offset += out.write(file_record.file_name.encode())
                    offset += out.write(b"\x00")

        # Write file data and set offest
        for folder_record in folder_records:
            for file_record in folder_record.files:
                file_record.offset = offset
                offset += file_record.write_data_block(out, self.archive_flags)

        # Re-write files section as we have file offsets now
        # TODO: read and edit offset only, do not rewrite everything
        offset = file_records_base
        out.seek(offset)
        for folder_record in folder_records:
            offset += out.write(bytes(BSAString(folder_record.value)))
            for file_record in folder_record.files:
                offset += out.write(file_record.block(self.archive_flags))
