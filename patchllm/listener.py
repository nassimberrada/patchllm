import speech_recognition as sr
import pyttsx3
from rich.console import Console

console = Console()
recognizer = sr.Recognizer()
tts_engine = pyttsx3.init()

def speak(text):
    console.print(f"🤖 Speaking: {text}", style="magenta")
    tts_engine.say(text)
    tts_engine.runAndWait()

def listen(prompt=None, timeout=5):
    with sr.Microphone() as source:
        if prompt:
            speak(prompt)
        console.print("🎙 Listening...", style="cyan")
        try:
            audio = recognizer.listen(source, timeout=timeout)
            text = recognizer.recognize_google(audio)
            console.print(f"🗣 Recognized: {text}", style="cyan")
            return text
        except sr.WaitTimeoutError:
            speak("No speech detected.")
        except sr.UnknownValueError:
            speak("Sorry, I didn’t catch that.")
        except sr.RequestError:
            speak("Speech recognition failed. Check your internet.")
    return None