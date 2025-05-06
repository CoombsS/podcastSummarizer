import os
import time
import io
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import sounddevice as sd
import wavio
import whisper
import openai
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from pathlib import Path

# =============== CONFIG ===============

openai.api_key = "YOURKEYHERE"
SPOTIFY_CLIENT_ID = "YOURSPOTIFYCLIENTID"
SPOTIFY_CLIENT_SECRET = "YOURSPOTIFYCLIENTSECRET"
PLAYLIST_ID = "PLAYLISTID"  # from your playlist URL you want to record/transcribe
EPISODE_LIMIT = 11 # Number of episodes to process
MODEL_NAME = "small"  # "base", "small", "medium", "large"
RECORDING_DIR = "recordings"
TRANSCRIPT_DIR = "transcripts"
PDF_OUTPUT = "podcast_summaries.pdf" # Output PDF file
VIRTUAL_CABLE_NAME = "CABLE Output"  # Your virtual cable name (e.g., "VB-Audio Virtual Cable" or "CABLE Output")

# ========== SETUP ==========

if not os.path.exists(RECORDING_DIR):
    os.makedirs(RECORDING_DIR)
if not os.path.exists(TRANSCRIPT_DIR):
    os.makedirs(TRANSCRIPT_DIR)

# ========== FUNCTIONS ==========

def fetch_playlist_episodes(playlist_id, limit=11):
    print("Fetching episodes from Spotify playlist...")
    auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
    sp = spotipy.Spotify(auth_manager=auth_manager)
    playlist = sp.playlist(playlist_id)
    tracks = playlist["tracks"]["items"]
    episodes = []
    for item in tracks[:limit]:
        track = item["track"]
        episodes.append({
            "name": track["name"],
            "url": track["external_urls"]["spotify"],
            "duration_ms": track["duration_ms"]
        })
    print(f"Retrieved {len(episodes)} episodes.")
    return episodes

def setup_browser():
    print("Launching Chrome browser...")

    user_data_path = str(Path(__file__).resolve().parent / "chrome_profile")

    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-data-dir={user_data_path}")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    return driver

def record_audio(filename, duration_sec, device_name=VIRTUAL_CABLE_NAME):
    print(f"Recording {duration_sec} seconds from virtual cable...")
    samplerate = 44100
    device = None

    # Find the device index based on name
    for idx, dev in enumerate(sd.query_devices()):
        if device_name.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
            device = idx
            break

    if device is None:
        raise RuntimeError(f"Input device '{device_name}' not found.")

    recording = sd.rec(int(duration_sec * samplerate), samplerate=samplerate, channels=2, device=device)
    sd.wait()
    wavio.write(filename, recording, samplerate, sampwidth=2)
    print(f"Saved recording to {filename}")

def transcribe_audio(file_path):
    print(f"Transcribing audio: {file_path}")
    model = whisper.load_model(MODEL_NAME)
    result = model.transcribe(file_path)
    return result["text"]

def summarize_text(text):
    print("Summarizing transcript with GPT...")
    prompt = f"Summarize the following podcast transcript:\n\n{text}"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{ "role": "user", "content": prompt }]
    )
    return response.choices[0].message.content.strip()

def generate_pdf(summaries, output_file):
    print("Generating PDF summary...")
    buffer = io.BytesIO()
    c = canvas.Canvas(output_file, pagesize=letter)
    width, height = letter
    for summary in summaries:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, height - 72, summary["title"])
        c.setFont("Helvetica", 10)

        y = height - 100
        for line in summary["content"].split("\n"):
            if y < 72:
                c.showPage()
                y = height - 72
            c.drawString(72, y, line)
            y -= 14
        c.showPage()
    c.save()
    print(f"PDF saved as: {output_file}")

def main():
    episodes = fetch_playlist_episodes(PLAYLIST_ID, EPISODE_LIMIT)
    summaries = []
    driver = setup_browser()

    for idx, ep in enumerate(episodes):
        print(f"\nEpisode {idx+1}/{len(episodes)}: {ep['name']}")
        print("Opening episode in browser...")
        driver.get(ep["url"])
        time.sleep(5)

        try:
            play_button = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Play']")
            play_button.click()
            print("Playback started.")
        except Exception as e:
            print("Could not click play button:", e)

        duration_sec = ep["duration_ms"] / 1000
        audio_file = os.path.join(RECORDING_DIR, f"episode_{idx+1}.wav")
        record_audio(audio_file, duration_sec)

        transcript = transcribe_audio(audio_file)
        transcript_path = os.path.join(TRANSCRIPT_DIR, f"episode_{idx+1}.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        print(f"Transcript saved: {transcript_path}")

        summary = summarize_text(transcript)
        summaries.append({
            "title": ep["name"],
            "content": summary
        })

    driver.quit()
    generate_pdf(summaries, PDF_OUTPUT)

if __name__ == "__main__":
    main()
