"""Build Talkie into a single executable using PyInstaller."""

import os

import PyInstaller.__main__
import customtkinter

# Get path to customtkinter to bundle its data (themes, fonts, etc.)
customtkinter_path = os.path.dirname(customtkinter.__file__)

PyInstaller.__main__.run([
    "main.py",
    "--name=Talkie",
    "--noconsole",
    "--onefile",
    "--paths=.",
    f"--add-data={customtkinter_path};customtkinter/",
    "--collect-all=sounddevice",
    "--collect-all=soundfile",
    "--collect-all=uiautomation",
    "--collect-all=pystray",
    "--collect-all=talkie_modules",
    "--collect-all=keyring",
    "--hidden-import=keyring.backends.Windows",
    "--hidden-import=dotenv",
    "--clean",
])
