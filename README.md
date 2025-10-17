# Java PDF Code Helper

Automate the process of generating, debugging, and fixing Java code from PDF-based specifications or prompts. This tool allows developers to quickly transform written instructions or problem descriptions into structured Java code, and iteratively refine it using AI-assisted feedback.

## Features

* **Automatic Java Code Generation**
  Converts PDF instructions into complete, compilable Java classes.

* **Fix Java Code with AI**
  Automatically processes compilation errors from Java files and generates corrected versions.

* **Debug Mode**
  Send your project code, custom prompts, and error messages to the AI to receive detailed debugging suggestions and improvements.

* **Flexible Output**
  Extracted Java files are saved with proper class names, while Markdown summaries of AI responses are kept for reference.

* **Configurable**
  Uses environment variables for API keys, models, and output directories.

## Requirements

* Python 3.9+
* Packages: `requests`, `python-dotenv`, `PyPDF2`
* OpenAI API key

```bash
pip install requests python-dotenv PyPDF2
```

## Setup

1. Clone the repository.
2. Create a `.env` file with your OpenAI API key:

```bash
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5-chat-latest  # optional, defaults to this model
OUTPUT_DIR=./output              # optional
```

3. Prepare your prompt (`prompt.txt`) and PDF file (`klausur.pdf`) in the project root.

## Usage

### 1. Generate Java Code from PDF

```bash
python3 generate_files.py
```

* Reads `prompt.txt` and `klausur.pdf`.
* Generates Java files in the output directory.
* Saves the AI response as a Markdown file.

### 2. Fix Existing Java Code

```bash
python3 generate_files.py --fix
```

* Reads all `.java` files in the output directory and `error.txt`.
* Sends them to the AI for correction.
* Saves fixed files and Markdown summary.

### 3. Debug Mode

```bash
python3 generate_files.py --debug
```

* Reads `debug.txt` (custom prompt) ad and `result.md` (project code).
* Sends them to the AI.
* Saves response in `response.md`.

### 4. Help

```bash
python3 generate_files.py --help
```

* Displays usage instructions and file requirements.

## Notes

* Java files are automatically named after their class names where possible.
* Markdown files contain the AI response for reference and debugging.
* Designed to assist in rapid Java code development from textual specifications.
