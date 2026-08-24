# EduComic Pro 🎨📚

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

![EduComic Pro UI Studio](."./generated_comics/comic_maxim_1.png")

Listen to a sample audio output created with the app:
<audio controls src="./generated_audio/maximum_subarray_problem__page_1.mp3"></audio>

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
