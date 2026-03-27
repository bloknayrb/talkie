"""Build Talkie into a single executable using PyInstaller."""

import ctypes.util
import os
import sys

import PyInstaller.__main__

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
    "tkinter",
]

exclude_args = []
for mod in EXCLUDE_MODULES:
    exclude_args.append(f"--exclude-module={mod}")

# Bundle VCRUNTIME140.dll so the exe works on machines without VC++ redist.
# libsndfile_x64.dll depends on it but PyInstaller doesn't trace native DLL deps.
vcruntime_args = []
vcruntime = ctypes.util.find_library("vcruntime140")
if vcruntime and os.path.isfile(vcruntime):
    vcruntime_args.append(f"--add-binary={vcruntime};.")
else:
    # Search common locations
    for d in [os.path.dirname(sys.executable), r"C:\Windows\System32"]:
        candidate = os.path.join(d, "vcruntime140.dll")
        if os.path.isfile(candidate):
            vcruntime_args.append(f"--add-binary={candidate};.")
            break

# Path to web_ui assets
web_ui_path = os.path.join("talkie_modules", "web_ui")

PyInstaller.__main__.run([
    "main.py",
    "--name=Talkie",
    "--noconsole",
    "--onefile",
    "--runtime-tmpdir=%LOCALAPPDATA%\\Talkie",
    "--icon=assets/talkie.ico",
    "--paths=.",
    f"--add-data={web_ui_path};talkie_modules/web_ui/",
    "--add-data=assets;assets/",
    "--collect-all=sounddevice",
    "--collect-all=soundfile",
    "--collect-all=uiautomation",
    "--collect-all=pystray",
    "--collect-all=talkie_modules",
    "--collect-all=keyring",
    "--collect-all=bottle",
    "--hidden-import=keyring.backends.Windows",
    "--hidden-import=dotenv",
    "--hidden-import=bottle",
    "--clean",
    *exclude_args,
    *vcruntime_args,
])
