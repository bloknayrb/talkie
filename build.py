"""Build Talkie into a single executable using PyInstaller."""

import os

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

# Path to web_ui assets
web_ui_path = os.path.join("talkie_modules", "web_ui")

PyInstaller.__main__.run([
    "main.py",
    "--name=Talkie",
    "--noconsole",
    "--onefile",
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
])
