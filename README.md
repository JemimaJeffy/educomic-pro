# EduComic Pro 🎨📚

> Turn complex topics and YouTube videos into engaging, age-appropriate educational comic strips using Google Gemini and OpenAI Whisper.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-%2320232a.svg?logo=react&logoColor=%2361DAFB)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?logo=fastapi)](https://fastapi.tiangolo.com/)

---

## ✨ Features

* **Multi-Source Input:** Generate custom comics from a simple text topic or by pasting any YouTube URL.
* **Video Intelligence:** Automatically downloads audio, transcribes it locally via Whisper, and extracts essential educational concepts.
* **Age Adaptation Engine:**
  * **Toddlers (2-5):** Simple words, cute vector art, and slow pacing.
  * **Kids (6-10):** Fun facts, vibrant cartoon style, and dynamic pacing.
  * **Teens (11+):** Witty dialogue, manga/anime style, and cinematic pacing.
* **Consistent Characters:** Leverages an iterative context window to preserve visual continuity across panels.
* **Modern Studio UI:** Professional dark-mode interface built with React and Tailwind CSS.
* **Live Console:** Terminal-style status logs to track the AI's "thought process" in real-time.

---

## 🛠️ Tech Stack

### Backend
* **Framework:** FastAPI (Python)
* **AI Models:** Google Gemini 2.0 Flash (Logic/Plot), Imagen 3 / Gemini Pro Vision (Image Generation)
* **Audio Processing:** yt-dlp, ffmpeg, openai-whisper (Local Transcription)
* **Image Processing:** Pillow (PIL)

### Frontend
* **Framework:** React (Create React App)
* **Styling:** Tailwind CSS v3
* **Icons:** Lucide React

---

## 🚀 Prerequisites

Ensure you have the following installed on your system before proceeding:
* Python 3.10+
* Node.js & npm
* FFmpeg (Required for audio/video processing)

---

## 💿 Installation & Setup

### 1. Backend Setup

Navigate to your project root and set up the Python virtual environment:

```bash
# Create and activate virtual environment
python -m venv venv
# On Mac/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies (numpy<2.0 is critical to avoid Whisper conflicts)
pip install fastapi uvicorn python-multipart python-dotenv google-genai pillow yt-dlp openai-whisper torch requests "numpy<2.0"
