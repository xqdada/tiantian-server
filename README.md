# TianTian Server

A FastAPI-based server supporting Edge TTS, ASR, and LLM services.

## Features

- **Edge TTS**: Text-to-speech using Microsoft Edge TTS.
- **ASR**: Automatic Speech Recognition.
- **LLM**: Language Model integration for advanced text processing.

## Configuration

The project uses a centralized configuration management system:

- **`config.yaml`**: Contains all service configurations (TTS, ASR, LLM, etc.).
- **`.env`**: Stores sensitive and environment-specific variables (e.g., API keys).

### Configuration Priority

1. Environment Variables
2. `config.yaml`
3. Default Values

## Setup

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure `config.yaml` and `.env` files.
4. Run the server:
   ```bash
   uvicorn main:app --reload
   ```

## Usage

- **TTS**: Use the `/tts` endpoint to convert text to speech.
- **ASR**: Use the `/asr` endpoint for speech recognition.
- **LLM**: Use the `/llm` endpoint for language model interactions.

## License

This project is licensed under the MIT License. 