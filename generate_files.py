import os
import re
import sys
import requests
from dotenv import load_dotenv
from datetime import datetime
from PyPDF2 import PdfReader

# === Konfiguration laden ===
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-chat-latest")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
PROMPT_FILE = "prompt.txt"
PDF_FILE = "klausur.pdf"
ERROR_FILE = "error.txt"
DEBUG_FILE = "debug.txt"
RESULT_FILE = os.path.join(OUTPUT_DIR, "result.md")
RESPONSE_FILE = os.path.join(OUTPUT_DIR, "response.md")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# === Hilfsfunktionen ===


def print_help():
    help_text = """
📘 Klausur Java Generator & Debug Tool

Verwendung:
  python3 klausurgen.py             → Generiert Java-Dateien aus PDF und Prompt
  python3 klausurgen.py --fix       → Liest vorhandene .java-Dateien und error.txt, sendet alles zur Korrektur
  python3 klausurgen.py --debug     → Liest debug.txt (Prompt) und result.md (Code), sendet alles an API und erstellt eine response.md mit der antwort
  python3 klausurgen.py --help      → Zeigt diese Hilfe an

Dateien & Umgebungsvariablen:
  prompt.txt       Enthält deine Aufgabenbeschreibung oder den Prompt
  klausur.pdf      PDF mit der Klausuraufgabe
  error.txt        Enthält Compiler-Fehler (nur für --fix / --debug)
  debug.txt        Freier Prompt für Debugging-Modus (--debug)
  result.md        Enthält deinen bestehenden Code (wird im Debug-Modus gesendet)
  .env             Muss OPENAI_API_KEY enthalten

Optionale ENV-Variablen:
  OPENAI_MODEL     z.B. gpt-5-chat-latest (Standard)
  OUTPUT_DIR       Zielverzeichnis für generierte Dateien (Standard: ./output)
"""
    print(help_text)


def call_openai(messages):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
    }

    print(f"🚀 Sende Anfrage an OpenAI mit Modell '{MODEL}'...")
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def pdf_to_text(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text


def save_java_files(reply, timestamp):
    code_blocks = re.findall(r"```java(.*?)```", reply, re.DOTALL)
    if not code_blocks:
        print("⚠️ Keine Java-Codeblöcke im Output gefunden.")
        return

    for block in code_blocks:
        class_names = re.findall(
            r"public\s+class\s+(\w+)|class\s+(\w+)", block)
        if not class_names:
            filename = os.path.join(OUTPUT_DIR, f"Unknown_{timestamp}.java")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(block.strip())
            print(f"💾 Java-Datei erstellt (unbenannt): {filename}")
        else:
            names = [name[0] or name[1] for name in class_names]
            for name in names:
                filename = os.path.join(OUTPUT_DIR, f"{name}.java")
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(block.strip())
                print(f"💾 Java-Datei erstellt: {filename}")


# === Hauptlogik ===
if "--help" in sys.argv:
    print_help()
    sys.exit(0)

elif "--fix" in sys.argv:
    print("🔧 Fix-Modus aktiviert.")

    # Alle Java-Dateien einlesen
    java_files = {}
    for fname in os.listdir(OUTPUT_DIR):
        if fname.endswith(".java"):
            with open(os.path.join(OUTPUT_DIR, fname), "r", encoding="utf-8") as f:
                java_files[fname] = f.read()

    if not java_files:
        print("⚠️ Keine Java-Dateien im Output-Ordner gefunden.")
        sys.exit(1)

    # Fehlertext einlesen
    if not os.path.exists(ERROR_FILE):
        print(f"⚠️ Fehlerdatei '{ERROR_FILE}' nicht gefunden.")
        sys.exit(1)

    with open(ERROR_FILE, "r", encoding="utf-8") as f:
        error_text = f.read().strip()

    code_summary = "\n\n".join(
        [f"// Datei: {n}\n{c}" for n, c in java_files.items()])
    fix_prompt = (
        "Du bist ein erfahrener Java-Entwickler. "
        "Hier sind mehrere Java-Dateien und eine Compiler-Fehlermeldung. "
        "Analysiere den Fehler und gib die korrigierten vollständigen Java-Dateien "
        "im Codeblock-Format (```java ... ```) zurück.\n\n"
        f"{code_summary}\n\nCompiler-Fehlermeldung:\n{error_text}"
    )

    messages = [
        {"role": "system", "content": "Du bist ein Java-Code-Fixer."},
        {"role": "user", "content": fix_prompt},
    ]

    reply = call_openai(messages)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_md = os.path.join(OUTPUT_DIR, f"fix_{timestamp}.md")
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(reply)
    print(f"✅ Fix-Ergebnis gespeichert in: {output_md}")

    save_java_files(reply, timestamp)
    print("🎉 Java-Dateien wurden mit den Korrekturen überschrieben.")

elif "--debug" in sys.argv:
    print("🐞 Debug-Modus aktiviert.")

    # Dateien prüfen
    if not os.path.exists(DEBUG_FILE):
        print(f"⚠️ Datei '{DEBUG_FILE}' nicht gefunden.")
        sys.exit(1)
    if not os.path.exists(RESULT_FILE):
        print(f"⚠️ Datei '{RESULT_FILE}' nicht gefunden.")
        sys.exit(1)

    # Dateien lesen
    with open(DEBUG_FILE, "r", encoding="utf-8") as f:
        debug_prompt = f.read().strip()
    with open(RESULT_FILE, "r", encoding="utf-8") as f:
        project_code = f.read()

    debug_input = (
        f"{debug_prompt}\n\n"
        "Hier ist der vollständige Projektcode (aus result.md):\n\n"
        f"{project_code}\n\n"
    )

    messages = [
        {"role": "system", "content": "Du bist ein erfahrener Softwareentwickler und Debugging-Assistent."},
        {"role": "user", "content": debug_input},
    ]

    reply = call_openai(messages)

    with open(RESPONSE_FILE, "w", encoding="utf-8") as f:
        f.write(reply)

    print(f"✅ Debug-Antwort gespeichert in: {RESPONSE_FILE}")

else:
    # === GENERATE-MODUS ===
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        custom_prompt = f.read().strip()

    exam_text = pdf_to_text(PDF_FILE)
    print(f"📘 PDF erfolgreich geladen ({len(exam_text.split())} Wörter).")

    messages = [
        {
            "role": "system",
            "content": "Du bist ein Java-Codegenerator. Antworte mit vollständigen, kompilierbaren und funktionierenden Java-Dateien im Codeblock.",
        },
        {
            "role": "user",
            "content": f"{custom_prompt}\n\nKlausuraufgabe:\n{exam_text}",
        },
    ]

    reply = call_openai(messages)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_md = os.path.join(OUTPUT_DIR, f"result_{timestamp}.md")
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(reply)
    print(f"✅ KI-Antwort gespeichert in: {output_md}")

    save_java_files(reply, timestamp)
