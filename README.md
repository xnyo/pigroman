# 📦✂️ Pigroman
## Package loose files into multiple Bethesda Archives

### 🐉 What is it
Pigroman takes loose files from your Skyrim Special Edition Mods (Skyrim Legendary Edition and Fallout 4 support may come in the future) and packages them into multiple BSA/BA2 files. This is useful if you have very large mods whose assets don't fit in a single BSA/BA2 file.

### 📂 How it works
Pigroman takes one or more "Data" subfolders as input. It then scans the directories recursively and adds files to a specific path up until a certain size threshold is reached. Once the archive is big enough, a new archive is created. Pigroman also calculates the hash of each file, aggregating identical files into the same archive, so identical files are not stored multiple times, making mods with the same assets smaller in some circumstances.
To create BSA/BA2 files, Pigroman uses Archive.exe, the packing utility included in the Creation Kit. Pigroman can also create empty .esl files for each archive. This is needed to load multiple BSA files in Skyrim Special Edition, since only one BSA file per esm/esp/esl is supported. The generated .esl files are totally empty and serve for the sole purpose to load the BSA files.

### ⚙️ Installing
You need Python 3.7 and pip to use Pigroman.
```
$ pip install -r requirements.txt
$ python pigroman.py --help
```

### 📑 Using
```
usage: pigroman.py [-h] [-z] [-s MAX_BLOCK_SIZE] [-e] -i DATA -f FOLDER
                   [FOLDER ...] -o OUTPUT_FOLDER -n OUTPUT_NAME -a
                   ARCHIVE_FOLDER

Splits and packs loose files in multiple Bethesda BSA files

optional arguments:
  -h, --help            show this help message and exit
  -z, --compress        Compresses the output archives
  -s MAX_BLOCK_SIZE, --max-block-size MAX_BLOCK_SIZE
                        Max size that an archive can assume before creating a
                        new archive. Note that the last archive can be up to
                        1/4 bigger than that. Default: 1G
  -e, --esl             Creates an .esl for each archive. Needed only when
                        working with Skyrim Special Edition. Not needed for
                        Fallout 4.
  -i DATA, --data DATA  Absolute path to the 'Data' folder. It must be a
                        folder called 'Data' with the game data structure.
  -f FOLDER [FOLDER ...], --folder FOLDER [FOLDER ...]
                        Subfolders to include in the archive. They can be
                        either absolute paths to data_folder's subfolders, or
                        folder names (eg: 'meshes'). Specify more folders
                        separated by a space to pack multiple folders.
  -o OUTPUT_FOLDER, --output-folder OUTPUT_FOLDER
                        BSAs (and ESLs) will be put in this folder.
  -n OUTPUT_NAME, --output-name OUTPUT_NAME
                        Base name of the output archives. An index will be
                        added at the end of each archive name.
  -a ARCHIVE_FOLDER, --archive-folder ARCHIVE_FOLDER
                        Absolute path to the folder that contains Archive.exe
```

### 👨‍🏫 Example
```
$ python pigroman.py -e -z -s 1.5G -i "C:\fast_vapore\Skyrim Special Edition\ModOrganizer\mods\SkyVac-lfs\data" -o D:\bsaout -n "skyvac models and textures" -a "C:\fast_vapore\Skyrim Special Edition\Tools\Archive" -f textures meshes
```
Creates compressed archives (-z) up to ~1.5GB size each (-s), taking `C:\fast_vapore\Skyrim Special Edition\ModOrganizer\mods\SkyVac-lfs\data` as data folder (-i), "textures"  and "meshes" subfolders (-f), placing the final archives inside "D:\bsaout" (-o),  naming them "skyvac models and textures0/1/2/3.bsa" (-n) and creating also "skyvac models and textures0/1/2/3.esl" (-e).


### 🏁 TODO
- [ ] Check Archive.exe logs to make sure that all files get added correctly
- [ ] Add support for multiple Archive.exe instances running in parallel
