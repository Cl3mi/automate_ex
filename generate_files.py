import os
import re
import sys
import requests
from dotenv import load_dotenv
from datetime import datetime
from PyPDF2 import PdfReader
import time

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


def _sanitize_filename(name: str) -> str:
    # Erlaubt nur Buchstaben, Zahlen und Unterstrich (kein Leerzeichen, kein Sonderzeichen)
    return re.sub(r'[^A-Za-z0-9_]', '_', name)

def _extract_package_and_imports(block: str) -> str:
    """Gibt die führenden package/import-Zeilen zurück (inkl. trailing newline)."""
    lines = block.splitlines()
    header_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("package ") or stripped.startswith("import "):
            header_lines.append(line)
        elif stripped == "":
            # leere Zeile nach header: beibehalten und weitersuchen (macht header lesbarer)
            if header_lines:
                header_lines.append(line)
            else:
                # noch kein header, ignoriere leere Zeilen am Anfang
                continue
        else:
            # erste "nicht package/import"-Zeile -> header endet
            break
    return ("\n".join(header_lines) + ("\n" if header_lines else ""))

def _find_declarations_with_spans(block: str):
    """
    Findet top-level declarations (class/interface/enum/record) und liefert
    tuples (kind, name, start_index_of_declaration).
    """
    pattern = re.compile(r'(?:^|\s)(public\s+|protected\s+|private\s+|static\s+|final\s+|abstract\s+|strictfp\s+)*'
                         r'(class|interface|enum|record)\s+([A-Za-z_]\w*)', re.MULTILINE)
    results = []
    for m in pattern.finditer(block):
        kind = m.group(2)
        name = m.group(3)
        start = m.start(2)  # Beginn bei 'class'/'interface'...
        results.append((kind, name, start))
    return results

def _find_matching_brace_end(s: str, start_index_of_open_brace: int) -> int:
    """
    Scannt ab dem Index der öffnenden '{' und gibt Index der schließenden '}' zurück,
    unter Berücksichtigung von Strings und Kommentaren (einfache, robuste Handhabung).
    Falls kein match gefunden wird, gibt -1 zurück.
    """
    i = start_index_of_open_brace
    depth = 0
    length = len(s)
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    while i < length:
        ch = s[i]
        nx = s[i+1] if i+1 < length else ''
        # Kommentarstart/ende
        if not in_single_quote and not in_double_quote:
            if not in_block_comment and ch == '/' and nx == '/':
                in_line_comment = True
                i += 1
            elif not in_line_comment and ch == '/' and nx == '*':
                in_block_comment = True
                i += 1
            elif in_line_comment and ch == '\n':
                in_line_comment = False
            elif in_block_comment and ch == '*' and nx == '/':
                in_block_comment = False
                i += 1
                # continue scanning after closing
        # Zitat-Handling (nur wenn nicht in Kommentaren)
        if not in_line_comment and not in_block_comment:
            if ch == '"' and not in_single_quote:
                # prüfe Escape
                escape_count = 0
                j = i - 1
                while j >= 0 and s[j] == '\\':
                    escape_count += 1
                    j -= 1
                if escape_count % 2 == 0:
                    in_double_quote = not in_double_quote
            elif ch == "'" and not in_double_quote:
                escape_count = 0
                j = i - 1
                while j >= 0 and s[j] == '\\':
                    escape_count += 1
                    j -= 1
                if escape_count % 2 == 0:
                    in_single_quote = not in_single_quote

            # Klammerzählung nur wenn wir nicht in einem String sind
            if not in_double_quote and not in_single_quote:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return i  # Index der schließenden '}'
        i += 1
    return -1

def save_java_files(reply, timestamp):
    """
    Parses AI output and writes .java files with proper filenames.
    - Uses // File: ... if available
    - Removes comments before class detection (so 'class' in comments won't trigger)
    - Supports class, interface, enum, and record
    """
    code_blocks = re.findall(r"```(?:java)?(.*?)```", reply, re.DOTALL | re.IGNORECASE)
    if not code_blocks:
        print("⚠️ Keine Java-Codeblöcke im Output gefunden.")
        return

    for idx, block in enumerate(code_blocks, start=1):
        original_block = block.strip()
        if not original_block:
            continue

        # --- 1️⃣ Look for explicit filename comment ---
        file_comment_match = re.search(
            r"//\s*File\s*:\s*([A-Za-z0-9_./\\-]+)", original_block, re.IGNORECASE
        )
        if file_comment_match:
            raw_name = file_comment_match.group(1).strip()
            # Add .java if not present
            if not raw_name.lower().endswith(".java"):
                raw_name += ".java"
            filename = os.path.join(OUTPUT_DIR, os.path.basename(raw_name))
        else:
            # --- 2️⃣ Remove comments before scanning for class/interface/enum/record ---
            # Remove all // ... and /* ... */ comments
            cleaned = re.sub(r"//.*?$|/\*.*?\*/", "", original_block, flags=re.DOTALL | re.MULTILINE)

            # Search for top-level declarations
            type_match = re.search(
                r"\b(?:public\s+)?(class|interface|enum|record)\s+([A-Za-z_]\w*)",
                cleaned,
            )

            if type_match:
                typename = type_match.group(2)
                filename = os.path.join(OUTPUT_DIR, f"{typename}.java")
            else:
                # --- 3️⃣ Fallback: Unknown file ---
                filename = os.path.join(OUTPUT_DIR, f"Unknown_{timestamp}_{idx}.java")

        # --- 4️⃣ Write file safely ---
        with open(filename, "w", encoding="utf-8") as f:
            f.write(original_block.strip() + "\n")

        print(f"💾 Datei erstellt: {filename}")


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
