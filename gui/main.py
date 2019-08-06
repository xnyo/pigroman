"""
This is some GUI stuff I've recycled from another project.
Don't look at the italian comments, they don't make sense and they'll go away once this is final.
"""
import json
import os
from collections import defaultdict, namedtuple
from tkinter import Tk, StringVar, IntVar, BooleanVar, Menu, filedialog, messagebox
from tkinter.ttk import Frame, Label, Entry, Button, Scale, Checkbutton, LabelFrame
from typing import Any, Dict

from utils import icons, conversions


class ConfigFile:
    def __init__(self, file_path: str, load: bool = True):
        self._config: Dict[str, Any] = {}
        self.file_path = file_path
        if load:
            self.load()

    def get(self, *args, **kwargs) -> Any:
        return self._config.get(*args, **kwargs)

    def __getitem__(self, item: str) -> Any:
        return self._config[item]

    def __setitem__(self, key: str, value: Any) -> None:
        self._config[key] = value

    def save(self) -> None:
        with open(self.file_path, "w") as f:
            f.write(json.dumps(self._config))

    def load_defaults(self) -> None:
        self._config = {"archive_tool_path": ""}

    def load(self) -> None:
        if not os.path.isfile(self.file_path):
            self.load_defaults()
            self.save()
        else:
            with open(self.file_path, "r") as f:
                self._config = json.loads(f.read())


class BrowseFrame(Frame):
    def __init__(self, master, variable, **kwargs):
        super(BrowseFrame, self).__init__(master, **kwargs)
        self.variable = variable
        self.master = master
        self.grid_columnconfigure(0, weight=1)
        self.entry = Entry(self, textvariable=self.variable)
        self.entry.grid(row=0, column=0, sticky="we")
        self.button = Button(
            self, image=icons.get_icon("folder.png"),
            command=lambda: self.variable.set(filedialog.askdirectory().replace("/", "\\"))
        ).grid(
            row=0, column=1, sticky="we"
        )


SubfolderEntry = namedtuple("FolderEntry", "var frame status_label")


class SubfoldersListFrame(Frame):
    """
    Frame con Entry degli autori
    """

    def __init__(self, master, data_path_var, add_empty_author_entry=True, **kwargs):
        """
        :param master:
        :param add_empty_author_entry: se `True`, aggiungi una Entry vuota in cima, altrimenti parti senza nessuna Entry
        :param kwargs:
        """
        super(SubfoldersListFrame, self).__init__(master, **kwargs)
        self.master = master

        self._subfolder_entries = []

        self.add_button = None

        self.data_path_var = data_path_var

        # Aggiungi entry vuota se richiesto
        if add_empty_author_entry:
            self.add_subfolder()

        # Pulsante 'Aggiungi autore'
        self.add_button = Button(self, image=icons.get_icon("add.png"), text="Add subfolder", compound="left",
                                 command=self.add_subfolder)
        self.add_button.pack(fill="x", pady=2)

    def add_subfolder(self, value=""):
        """
        Aggiungi un autore

        :param value: nome dell'autore
        :return:
        """
        # Rimuovi pulsante 'Aggiungi autore', se è stato posizionato
        if self.add_button is not None:
            self.add_button.pack_forget()

        # Crea frame con Entry e pulsante rimozione e posizionali
        f = Frame(self)
        status_label = Label(f, image=icons.get_icon("warning.png"))
        ae = SubfolderEntry(StringVar(value=value), f, status_label)
        self._subfolder_entries.append(ae)
        f.grid_columnconfigure(1, weight=1)
        ae.status_label.grid(row=0, column=0, sticky="we")
        ae.var.trace("w", lambda *_: self.update_entry_status_label(ae))
        Entry(f, textvariable=self._subfolder_entries[-1].var).grid(row=0, column=1, sticky="we")
        Button(
            f, image=icons.get_icon("search.png"),
            command=lambda: ae.var.set(f"{self.data_path_var.get().strip()}\\{ae.var.get().strip()}")
        ).grid(row=0, column=2, sticky="e")
        Button(
            f, image=icons.get_icon("folder.png"),
            command=lambda: ae.var.set(filedialog.askdirectory().replace("/", "\\").strip())
        ).grid(row=0, column=3, sticky="e")
        Button(
            f, image=icons.get_icon("delete.png"),
            command=lambda: self.remove_subfolder(ae)
        ).grid(row=0, column=4, sticky="e")
        f.pack(fill="x", pady=1, expand=True)

        # Riaggiungi pulsante 'Aggiungi autore', se necessario
        if self.add_button is not None:
            self.add_button.pack(fill="x", pady=2)

    def is_subfolder(self, path: str) -> bool:
        data_path = self.data_path_var.get().lower().rstrip("\\").strip()
        return bool(data_path) and path.lower().strip().startswith(data_path) and os.path.isdir(path)

    def update_entry_status_label(self, entry: SubfolderEntry) -> None:
        entry.status_label.configure(
            image=icons.get_icon(
                "success.png"
                if self.is_subfolder(entry.var.get()) else
                "warning.png"
            )
        )

    def remove_subfolder(self, author_entry):
        """
        Rimuove un autore dalla lista degli autori

        :param author_entry: `AutorEntry` dell'autore da rimuovere
        :return:
        """
        author_entry.frame.pack_forget()
        self._subfolder_entries.remove(author_entry)

    @property
    def subfolders(self):
        """
        Ritorna gli autori
        :return:
        """
        return self._subfolder_entries

    @subfolders.setter
    def subfolders(self, authors):
        """
        Imposta gli autori e ricostruisce la lista dei widget

        :param authors:
        :return:
        """
        self._subfolder_entries.clear()
        for widget in self.pack_slaves():
            widget.pack_forget()
        for author in authors:
            self.add_subfolder(author)

    def reevaluate_statuses(self):
        for x in self._subfolder_entries:
            self.update_entry_status_label(x)


class MainFrame(Frame):
    MIN_ARCHIVE_SIZE = 100 * 1024
    MAX_ARCHIVE_SIZE = 2.5 * 1024 * 1024

    def __init__(self, master, **kwargs):
        super(MainFrame, self).__init__(master, **kwargs)
        self.master = master

        # Configurazione griglia
        self.grid_columnconfigure(0, weight=1, pad=10)
        self.grid_columnconfigure(1, weight=5, pad=10)
        self.grid_columnconfigure(2, weight=1, pad=10)
        # for i in range(0, 10):
        #     self.grid_rowconfigure(i, pad=0, weight=1)

        # Titolo
        # Label(self, text="Pigroman", font=("Segoe UI", 16), image=icons.get_icon("icon.png"),
        # compound="left").grid(row=0, column=0, padx=(0, 30), sticky="w")

        self.data_path = StringVar()
        self.data_path.trace(
            "w", lambda *_: self.subfolders_list_frame.reevaluate_statuses()
        )
        self.output_path = StringVar()
        self.output_name = StringVar()
        self.max_block_size = IntVar()
        self.max_block_size.trace(
            "w", lambda *_: self.max_archive_size_label.configure(
                text=conversions.number_to_readable_size(self.max_block_size.get())
            )
        )
        self.compress = BooleanVar()
        self.create_esl = BooleanVar()
        self.file_types = defaultdict(BooleanVar)

        Label(self, text="Data path").grid(row=1, column=0, sticky="w")
        BrowseFrame(self, self.data_path).grid(row=1, column=1, sticky="we", columnspan=4)

        Label(self, text="Output path").grid(row=2, column=0, sticky="w")
        BrowseFrame(self, self.output_path).grid(row=2, column=1, sticky="we", columnspan=4)

        Label(self, text="Output name").grid(row=3, column=0, sticky="w")
        Entry(self, textvariable=self.output_name).grid(row=3, column=1, sticky="we", columnspan=2)

        Label(self, text="Max archive size").grid(row=4, column=0, sticky="w")
        Scale(
            self, from_=self.MIN_ARCHIVE_SIZE, to=self.MAX_ARCHIVE_SIZE, variable=self.max_block_size
        ).grid(row=4, column=1, sticky="we")
        self.max_archive_size_label = Label(self)
        self.max_archive_size_label.grid(row=4, column=2, sticky="e")

        self.folders_group = LabelFrame(self, text="Subfolders")
        self.folders_group.grid(row=5, column=0, columnspan=5, sticky="nswe")
        self.subfolders_list_frame = SubfoldersListFrame(self.folders_group, self.data_path)
        self.subfolders_list_frame.pack(fill="both")

        self.options_group = LabelFrame(self, text="Options")
        self.options_group.grid(row=6, column=0, sticky="nswe", columnspan=3)
        Checkbutton(self.options_group, text="Compress", variable=self.compress).pack(side="left")
        Checkbutton(self.options_group, text="Create ESLs", variable=self.create_esl).pack(side="left")

        self.file_types_group = LabelFrame(self, text="File types (coming soon)")
        self.file_types_group.grid(row=7, column=0, sticky="nswe", columnspan=4)
        r = 0
        c = 0
        for i, x in enumerate(("Meshes", "Textures", "Menus", "Sounds", "Voices", "Shaders", "Trees", "Fonts", "Misc")):
            Checkbutton(self.file_types_group, text=x, variable=self.file_types[x.lower()], state="disabled").grid(
                row=r, column=c, sticky="we"
            )
            c += 1
            if c == 3:
                c = 0
                r += 1

        self.build_button = Button(
            self, text="Create packages!", image=icons.get_icon("save.png"),
            compound="left", command=self.build
        )
        self.build_button.grid(
            row=8, column=0, columnspan=4, sticky="we"
        )

        self.max_block_size.set(1.5 * 1024 * 1024)

    def build(self):
        try:
            self.master.check_archive()
            self.check_settings()
            self.build_button.config(state="disabled")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
        finally:
            self.build_button.config(state="enabled")

    def check_settings(self):
        if not self.data_path.get().lower().strip().endswith("data"):
            raise ValueError("The data path must be a folder named 'data'.")
        if not os.path.isdir(self.data_path.get()):
            raise ValueError("The data path does not exist.")
        if not os.path.isdir(self.output_path.get()):
            raise ValueError("The output path does not exist.")
        if not self.MIN_ARCHIVE_SIZE < self.max_block_size.get() < self.MAX_ARCHIVE_SIZE:
            raise ValueError("The archive size must be between 100MB and 2.5GB")
        if not self.output_name.get().strip():
            raise ValueError("Invalid output name")
        if not [x for x in self.subfolders_list_frame.subfolders if bool(x.var.get().strip())]:
            raise ValueError("No subfolders specified")
        for subfolder in self.subfolders_list_frame.subfolders:
            path = subfolder.var.get()
            if not self.subfolders_list_frame.is_subfolder(path):
                raise ValueError(f"{path} is not a data subfolder or does not exist!")


class MainWindow(Tk):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.minsize(250, 280)
        self.title("Pigroman")
        self.config_file = ConfigFile("config.json", load=True)
        if os.name == "nt":
            self.iconbitmap("icons/app.ico")

        mb = Menu(self)
        fm = Menu(mb, tearoff=0)
        fm.add_command(label="Set Archive.exe path", command=self.set_archive_path)
        fm.add_command(label="Save these settings", command=self.save_preset)
        mb.add_cascade(label="File", menu=fm)
        self.config(menu=mb)

        self.main_frame = MainFrame(self)
        self.main_frame.pack(fill="both", padx=10, pady=10)

    def set_archive_path(self):
        file_path = filedialog.askopenfilename(filetypes=[("Archive.exe", "Archive.exe")])
        file_path = file_path.replace("/", "\\")
        if not file_path.endswith("Archive.exe"):
            messagebox.showerror("Invalid path", "Please select Archive.exe")
            return
        folder = "\\".join(file_path.split("\\")[:-1])
        messagebox.showinfo("Success", f"Archive.exe path set to {folder}\\Archive.exe")
        self.config_file["archive_tool_path"] = folder
        self.config_file.save()

    def check_archive(self):
        archive_path = self.config_file.get("archive_tool_path", "")
        if not archive_path:
            raise ValueError("You must set Archive.exe's path first.")
        elif not os.path.isfile(f"{archive_path}\\Archive.exe"):
            raise ValueError(f"File not found: {archive_path}\\Archive.exe")

    def save_preset(self):
        messagebox.showinfo("Success", "Current settings saved as default.")
