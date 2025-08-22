import speech_recognition as sr
import pyttsx3

recognizer = sr.Recognizer()
tts_engine = pyttsx3.init()

def speak(text):
    print("🤖 Speaking:", text)
    tts_engine.say(text)
    tts_engine.runAndWait()

def listen(prompt=None, timeout=5):
    with sr.Microphone() as source:
        if prompt:
            speak(prompt)
        print("🎙 Listening...")
        try:
            audio = recognizer.listen(source, timeout=timeout)
            text = recognizer.recognize_google(audio)
            print(f"🗣 Recognized: {text}")
            return text
        except sr.WaitTimeoutError:
            speak("No speech detected.")
        except sr.UnknownValueError:
            speak("Sorry, I didn’t catch that.")
        except sr.RequestError:
            speak("Speech recognition failed. Check your internet.")
    return None
