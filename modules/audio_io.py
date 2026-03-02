import os
import numpy as np
import soundfile as sf
import sounddevice as sd
import threading
import queue

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')
START_WAV = os.path.join(ASSETS_DIR, 'start.wav')
STOP_WAV = os.path.join(ASSETS_DIR, 'stop.wav')
SAMPLE_RATE = 44100

def _generate_tone(filename, freq_start, freq_end, duration=0.2):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    # Frequency modulation
    frequencies = np.linspace(freq_start, freq_end, len(t))
    # Generate phase
    phase = np.cumsum(frequencies) * 2 * np.pi / SAMPLE_RATE
    audio = np.sin(phase)
    
    # Apply envelope (fade in / fade out) to avoid clicks
    attack_time = 0.05
    decay_time = 0.05
    attack_samples = int(attack_time * SAMPLE_RATE)
    decay_samples = int(decay_time * SAMPLE_RATE)
    
    envelope = np.ones_like(audio)
    envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
    envelope[-decay_samples:] = np.linspace(1, 0, decay_samples)
    
    audio = audio * envelope * 0.5 # 0.5 amplitude
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    sf.write(filename, audio, SAMPLE_RATE)

def ensure_assets():
    if not os.path.exists(START_WAV):
        _generate_tone(START_WAV, 440, 880) # Ascending
    if not os.path.exists(STOP_WAV):
        _generate_tone(STOP_WAV, 880, 440) # Descending

def play_start_chime():
    data, fs = sf.read(START_WAV)
    sd.play(data, fs)

def play_stop_chime():
    data, fs = sf.read(STOP_WAV)
    sd.play(data, fs)

_recording = False
_audio_queue = queue.Queue()
_recording_thread = None
_recorded_data = []

def _record_callback(indata, frames, time, status):
    if status:
        pass # Ignore status for now
    if _recording:
        _audio_queue.put(indata.copy())

def start_recording():
    global _recording, _audio_queue, _recorded_data, _recording_thread
    _recording = True
    _recorded_data = []
    # Clear queue
    while not _audio_queue.empty():
        _audio_queue.get()
        
    def record_loop():
        with sd.InputStream(samplerate=16000, channels=1, callback=_record_callback):
            while _recording:
                sd.sleep(100)
    
    _recording_thread = threading.Thread(target=record_loop, daemon=True)
    _recording_thread.start()
    play_start_chime()

def stop_recording():
    global _recording, _recording_thread, _recorded_data
    _recording = False
    play_stop_chime()
    if _recording_thread:
        _recording_thread.join()
        
    while not _audio_queue.empty():
        _recorded_data.append(_audio_queue.get())
        
    if _recorded_data:
        return np.concatenate(_recorded_data, axis=0)
    return np.array([])
