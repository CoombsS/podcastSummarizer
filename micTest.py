import sounddevice as sd

# List all audio devices
devices = sd.query_devices()
for idx, device in enumerate(devices):
    print(f"{idx}: {device}")
