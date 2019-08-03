from tkinter import PhotoImage

ICONS = {}


def get_icon(icon):
    if icon not in ICONS:
        ICONS[icon] = PhotoImage(file=r"icons/{}".format(icon))
    return ICONS[icon]
