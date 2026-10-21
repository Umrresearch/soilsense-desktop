"""SoilSense desktop — run with:  python main.py"""
import tkinter as tk

from soilsense.app import App


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
