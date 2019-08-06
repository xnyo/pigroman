import argparse
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from threading import Thread
from typing import Dict, List, Set

from cached_property import cached_property
import xxhash

from utils import conversions


def is_ascii(s: str) -> bool:
    """
    A function that checks whether a string contains
    only ASCII characters

    :param s: input string
    :return: True if it contains only ASCII characters, False otherwise.
    """
    return all(ord(c) < 128 for c in s)


class File:
    """
    A class representing a file that will be packet
    """

    def __init__(self, path: str, base_dir: str, size: int):
        """
        Initializes a new File object

        :param path: absolute path of the file
        :param base_dir: absolute base (Data) path
        :param size: size of the file, in bytes
        """
        self.path = path.lower().strip()
        self.base_dir = base_dir.lower().strip()
        self.size = size
        self.copied = False

    @property
    def relative_path(self) -> str:
        """
        Returns this file's path, relative to the "Data" folder

        :return:
        """
        if not self.path.startswith(self.base_dir):
            raise RuntimeError(f"The files must be in the base dir ({self.path}, base dir is {self.base_dir})")
        return self.path[len(self.base_dir):].lstrip("\\").strip()

    @cached_property
    def hash(self) -> int:
        """
        Cached property containing the xxhash of the file

        :return:
        """
        with open(self.path, "rb") as f:
            return xxhash.xxh64_intdigest(f.read())

    def __repr__(self) -> str:
        return f"<File {self.path} [{self.hash}]>"

    @property
    def cli_format(self):
        return f"{self.relative_path}\n"


def archive_work(
    block_i: int, archive_tool_path: str, compress: bool, data_path: str, output_folder: str, output_name: str
) -> None:
    # Write script
    with open(f"{archive_tool_path}\\script_{block_i}.txt", "w") as f:
        # TODO: Automatically determine CHECKs
        for x in (
            f"Log: log_{block_i}.txt",
            "New Archive",
            "Check: Textures",
            "Check: Meshes",
            "Check: Voices",
            "Check: Sounds",
            "Check: Misc",
            "Check: Compress Archive" if compress else "",
            f"Set File Group Root: {data_path}\\",
            f"Add File Group: {archive_tool_path}\\files_{block_i}.txt",
            f"Save Archive: {output_folder}\\{output_name}{block_i if block_i > 0 else ''}.bsa"
        ):
            f.write(f"{x}\r\n")

    # Copy the files list
    shutil.copy(f"out_{block_i}.txt", f"{archive_tool_path}\\files_{block_i}.txt")

    # Execute Archive.exe, and provide it the script
    subprocess.run([f"{archive_tool_path}\\Archive.exe", f"script_{block_i}.txt"], cwd=archive_tool_path)

    # Delete temp script and files list
    os.remove(f"{archive_tool_path}\\script_{block_i}.txt")
    os.remove(f"{archive_tool_path}\\files_{block_i}.txt")


def check_and_sanitize_data_subfolders(data_path: str, subfolders: List[str]) -> None:
    for i in range(len(subfolders)):
        subfolders[i] = subfolders[i].strip().rstrip("\\").lower()
        if not subfolders[i].startswith(data_path):
            subfolders[i] = f"{data_path}\\{subfolders[i]}"
            if not os.path.isdir(subfolders[i]):
                raise ValueError(f"{subfolders[i]} is not inside data path")


def main(
    data_path: str, folders_to_pack: List[str], output_folder: str,
    output_name: str, archive_tool_path: str, max_block_size: int = 700 * 1024 * 1024,
    compress: bool = False, create_esl: bool = True,
    max_workers: int = 1, aggregate_duplicates: bool = False,
    folders_to_ignore: List[str] = None,
) -> None:
    """


    :param data_path: absolute path to a folder called "Data" that contains the game data structure.
    :param folders_to_pack: iterable of folder to pack.
                           Can be either an absolute paths (that's a data_path's subfolder
                           or simply the name of a subfolder)
    :param output_folder: absolute path to the output folder
    :param output_name: name of the output archives. Will append a number, starting from 0.
    :param archive_tool_path: absolute path of the folder containing Archive.exe
    :param max_block_size: max size, in bytes, that an archive can assume before creating a new archive.
                           note that the last archive can be up to 1/4 bigger than that.
    :param compress: if True, the archive will be compressed. If False, it won't.
    :return:
    """
    # Sanitize output folder
    output_folder = output_folder.rstrip("\\").strip()

    # Sanitize data path, and make sure it's called "Data"
    data_path = data_path.rstrip("\\").strip().lower()
    if not data_path.endswith("data"):
        raise ValueError("Data path must be a folder called Data")

    # Check all folders to pack. They must be data_path's subfolders
    check_and_sanitize_data_subfolders(data_path, folders_to_pack)
    # for i in range(len(folders_to_pack)):
    #     folders_to_pack[i] = folders_to_pack[i].strip().lower()
    #     if not folders_to_pack[i].startswith(data_path):
    #         folders_to_pack[i] = f"{data_path}\\{folders_to_pack[i]}"
    #         if not os.path.isdir(folders_to_pack[i]):
    #             raise ValueError("Folder to pack must be inside data path")

    # Check all folders to ignore
    if folders_to_ignore is None:
        folders_to_ignore = []
    check_and_sanitize_data_subfolders(data_path, folders_to_ignore)

    # xxhash -> set of duplicate 'File's
    duplicates: Dict[int, Set[File]] = defaultdict(set)

    # BSA archives
    blocks: List[List[File]] = []

    # absolute file path -> 'File'
    files: Dict[str, File] = {}

    # Total files counter, used to show progress every 1000 processed files
    total_i = 0

    # Current block variables
    block_size = 0
    block_size_bytes = 0
    block_files: List[File] = []

    # Process each folder
    for folder_to_pack in folders_to_pack:
        # Each subfolder
        for root, dirs, files_ in os.walk(folder_to_pack):
            # Make sure this subfolder is not ignored
            if any(root.lower().startswith(f_i) for f_i in folders_to_ignore):
                print(f"! Skipped subfolder {root}")
                continue

            # And each file
            for file in files_:
                file_path = os.path.join(os.sep, root, file).lower()

                # Make sure the file is valid
                # TODO: Other filters
                if not os.path.isfile(file_path) \
                        or file_path.split("\\")[-1].startswith(".") \
                        or os.path.islink(file_path):
                    print(f"! Skipped {file_path}")
                    continue

                # Print a warning if the file name contains non-ascii characters, as they may cause issues
                if not is_ascii(file_path):
                    print(f"! Non-ASCII file name ({file_path})")
                total_i += 1
                file_size = os.path.getsize(file_path)

                # Create a File object
                file_object = File(
                    file_path,
                    base_dir=data_path,
                    size=file_size
                )

                # Add it to the duplicates defaultdict...
                if aggregate_duplicates:
                    duplicates[file_object.hash].add(file_object)

                # ...to the path -> File dictionary...
                files[file_object.path] = file_object

                # ...and to the current block's files
                block_files.append(file_object)

                # Also increase the size in bytes and number of files of this block
                block_size_bytes += file_size
                block_size += file_size

                if block_size >= max_block_size:
                    # Block exceeded max size, create a permanent new block
                    print(f"+ Created a new block with {len(block_files)} files, { block_size_bytes / 1024 / 1024 } MB")
                    blocks.append(block_files)

                    # Reset local block variables
                    block_files = []
                    block_size = 0
                    block_size_bytes = 0

                # Print progress every 1000 items
                if total_i % 1000 == 0:
                    print(f"* Processed {total_i} files")

    # No more files to process.
    # Make the last local block permanent
    # Or add the files in the local block to the last permanent block if they're few
    if block_files:
        if block_size < max_block_size / 4 and blocks:
            blocks[-1].extend(block_files)
            size_bytes = sum(x.size for x in blocks[-1])
            print(
                f"+ Merged last block ({len(block_files)} files) with "
                f"2nd last one, now { size_bytes / 1024 / 1024 } MB"
            )
        else:
            print(f"+ Created last block with {len(block_files)} files, { block_size_bytes / 1024 / 1024} MB")
            blocks.append(block_files)

    # Create a file lists for each block
    for i, block in enumerate(blocks):
        with open(f"out_{i}.txt", "w") as f:
            for file in block:
                if file.copied:
                    # This file has already been copied, do not put it in this block
                    continue
                f.write(file.cli_format)

                # This file gets copied now
                file.copied = True

                # Copy all its duplicates as well if we're in aggregate mode
                if aggregate_duplicates:
                    for duplicate in duplicates[file.hash]:
                        if duplicate.path == file.path:
                            # That's us, not a duplicate
                            continue

                        # Actual duplicate, copy it as well
                        f.write(duplicate.cli_format)
                        duplicate.copied = True

    # Calculate duplicates and saved size
    print(f"\n* Created file lists for {len(blocks)} blocks")
    c = 0
    w = 0
    for k, v in duplicates.items():
        if len(v) > 1:
            c += len(v) - 1
            w += files[next(iter(v)).path].size
    print(f"* Total duplicates: {c}")
    print(f"* Saved size: {w / 1024 / 1024} MB")

    # Pack files with Archive.exe
    # if input("Do you want to pack the files? [y/N]").lower().strip() != "y":
    #     return
    workers: Set[Thread] = set()
    for i, block in enumerate(blocks):
        print(f"* Packing block {i+1}/{len(blocks)}")
        w = Thread(
            target=lambda: archive_work(
                i,
                archive_tool_path=archive_tool_path, compress=compress,
                data_path=data_path, output_folder=output_folder, output_name=output_name
            )
        )
        workers.add(w)
        w.start()

        # Wait for some worker to finish before spawning new ones
        while len(workers) >= max_workers:
            to_remove = set()
            for w in workers:
                w.join(timeout=1)
                if not w.is_alive():
                    to_remove.add(w)
            workers -= to_remove

    # Wait for any remaining workers
    for w in workers:
        w.join()

    # Delete temp .bsl files left over by Archive.exe
    print("* Deleting .bsl files")
    for file in os.listdir(output_folder):
        if file.endswith(".bsl"):
            os.remove(os.path.join(output_folder, file))

    # Create an .esl file for each archive
    # if input("Do you want to create .esl files [y/N]").lower().strip() != "y":
    #     return
    if create_esl:
        print("* Creating .esl files")
        for file in os.listdir(output_folder):
            if file.endswith(".bsa"):
                file_name = file.split("\\")[-1].split(".")[0]
                shutil.copy("empty.esl", f"{output_folder}\\{file_name}.esl")


def cast_workers_number(x: str) -> int:
    x = int(x)
    if x <= 0:
        raise argparse.ArgumentTypeError("Workers number must be > 0")
    return x


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Splits and packs loose files in multiple Bethesda BSA files")
    parser.add_argument(
        "-z",
        "--compress",
        action="store_true",
        help="Compresses the output archives",
        default=False,
        required=False
    )
    parser.add_argument(
        "-zz",
        "--aggregate-duplicates",
        action="store_true",
        help="Experimental option that aggregates identical files into the same archive. "
             "Archive.exe seems to ignore this.",
        default=False,
        required=False
    )
    parser.add_argument(
        "-s",
        "--max-block-size",
        help="Max size that an archive can assume before creating a new archive. "
             "Note that the last archive can be up to 1/4 bigger than that. Default: 1G",
        default="1G",
        required=False
    )
    parser.add_argument(
        "-e",
        "--esl",
        help="Creates an .esl for each archive.",
        action="store_true",
        default=False,
        required=False
    )
    parser.add_argument(
        "-i",
        "--data",
        help="Absolute path to the 'Data' folder. "
             "It must be a folder called 'Data' "
             "with the game data structure.",
        required=True
    )
    parser.add_argument(
        "-f",
        "--folder",
        nargs="+",
        help="Subfolders to include in the archive. "
             "They can be either absolute paths to data_folder's subfolders, or "
             "folder names (eg: 'meshes'). Specify more folders separated by a "
             "space to pack multiple folders.",
        required=True
    )
    parser.add_argument(
        "-nf",
        "--not-folder",
        nargs="+",
        help="Subfolders to exclude in the archive.",
        required=False
    )
    parser.add_argument(
        "-o",
        "--output-folder",
        help="BSAs (and ESLs) will be put in this folder.",
        required=True
    )
    parser.add_argument(
        "-n",
        "--output-name",
        help="Base name of the output archives. An index will be added at the end of each archive name.",
        required=True
    )
    parser.add_argument(
        "-a",
        "--archive-folder",
        help="Absolute path to the folder that contains Archive.exe",
        required=True
    )
    parser.add_argument(
        "-p",
        "--parallel",
        help="Specified how many Archive.exe instances can be running at the same time",
        type=cast_workers_number,
        default=1,
        required=False
    )
    args = parser.parse_args()
    max_block_size = conversions.readable_size_to_number(args.max_block_size)
    st = time.monotonic()
    print(f"# Data path: {args.data}")
    print(f"# Folders to pack: {args.folder}")
    print(f"# Folders NOT to pack: {args.not_folder}")
    print(f"# Output folder: {args.output_folder}")
    print(f"# Output base name: {args.output_name}[...].bsa")
    print(f"# Archive tool path: {args.archive_folder}")
    print(f"# Create ESL: {args.esl}")
    print(f"# Compress: {args.compress}")
    print(f"# Aggregating: {args.aggregate_duplicates}")
    print(f"# Max block size: ~{max_block_size / 1024 / 1024} MB "
          f"(up to {(max_block_size + max_block_size / 4) / 1024 / 1024} MB)")
    if not os.path.isfile(f"{args.archive_folder}\\Archive.exe"):
        sys.exit(f"Cannot find Archive.exe in {args.archive_folder}")
    print()
    main(
        data_path=args.data,
        folders_to_pack=args.folder,
        folders_to_ignore=args.not_folder,
        output_folder=args.output_folder,
        output_name=args.output_name,
        archive_tool_path=args.archive_folder,
        create_esl=args.esl,
        compress=args.compress,
        max_block_size=max_block_size,
        max_workers=args.parallel,
        aggregate_duplicates=args.aggregate_duplicates
    )
    et = time.monotonic()
    print(f"* Took {et - st} s")
