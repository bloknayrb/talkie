"""Build Talkie into a single executable using PyInstaller."""

import os

import PyInstaller.__main__
import customtkinter

# Get path to customtkinter to bundle its data (themes, fonts, etc.)
customtkinter_path = os.path.dirname(customtkinter.__file__)

# Packages that are NOT used by Talkie but commonly installed globally.
# Excluding these prevents PyInstaller from pulling in hundreds of MB of junk.
EXCLUDE_MODULES = [
    "torch",
    "tensorflow",
    "scipy",
    "pandas",
    "matplotlib",
    "onnxruntime",
    "sympy",
    "sqlalchemy",
    "pyarrow",
    "cv2",
    "opencv",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "py",
    "pygments",
    "lxml",
    "openpyxl",
    "dns",
]

exclude_args = []
for mod in EXCLUDE_MODULES:
    exclude_args.append(f"--exclude-module={mod}")

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
    *exclude_args,
])
