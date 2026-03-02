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
    '--paths=.',
    f'--add-data={customtkinter_path};customtkinter/',
    '--collect-all=sounddevice',
    '--collect-all=soundfile',
    '--collect-all=uiautomation',
    '--collect-submodules=talkie_modules',
    '--hidden-import=talkie_modules.api_client',
    '--hidden-import=talkie_modules.audio_io',
    '--hidden-import=talkie_modules.config_manager',
    '--hidden-import=talkie_modules.context_capture',
    '--hidden-import=talkie_modules.hotkey_manager',
    '--hidden-import=talkie_modules.settings_ui',
    '--hidden-import=talkie_modules.text_injector',
    '--hidden-import=pystray._win32',
    '--clean'
])
