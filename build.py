import PyInstaller.__main__
import customtkinter
import os

# Get path to customtkinter to bundle its data (themes, fonts, etc.)
customtkinter_path = os.path.dirname(customtkinter.__file__)

PyInstaller.__main__.run([
    'main.py',
    '--name=Talkie',
    '--noconsole',
    '--onefile',
    f'--add-data={customtkinter_path};customtkinter/',
    '--collect-all=sounddevice',
    '--collect-all=soundfile',
    '--clean'
])
