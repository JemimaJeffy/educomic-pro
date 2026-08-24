EduComic Pro 🎨📚
EduComic Pro is an AI-powered educational tool that turns complex topics or YouTube videos into engaging, age-appropriate comic strips.
Designed for educators, parents, and students, it uses Google Gemini for storytelling and image generation, and OpenAI Whisper for video transcription.
✨ Features
Multi-Source Input: Generate comics from a simple text topic or by pasting a YouTube URL.
Video Intelligence: Automatically downloads audio, transcribes it locally using Whisper, and extracts key educational concepts.
Age Adaptation Engine :
Toddlers (2-5): Simple words, cute vector art, slow pacing.
Kids (6-10): Fun facts, vibrant cartoon style, dynamic pacing.
Teens (11+): Witty dialogue, manga/anime style, cinematic pacing.
Consistent Characters: Uses an iterative context window to keep visual consistency across panels.
Modern UI: Professional "Dark Mode" studio interface built with React and Tailwind CSS.
Live Console: Terminal-style status logs to track the AI's "thought process" in real-time.
🛠️ Tech Stack
Backend
Framework: FastAPI (Python)
AI Models: Google Gemini 2.0 Flash (Logic/Plot), Imagen 3 / Gemini Pro Vision (Image Generation)
Audio Processing: yt-dlp (YouTube Download), ffmpeg (Audio conversion), openai-whisper (Local Transcription)
Image Processing: Pillow (PIL)
Frontend
Framework: React (Create React App)
Styling: Tailwind CSS v3
Icons: Lucide React
🚀 Prerequisites
Before running the project, ensure you have the following installed:
Python 3.10+
Node.js & npm
FFmpeg (Required for audio processing)

💿 Installation
Backend Setup
Navigate to the project root and create a virtual environment:

Create virtual env
python -m venv venv
Activate (Mac/Linux)
source venv/bin/activate
Activate (Windows)
venv\Scripts\activate

Install the dependencies:
pip install fastapi uvicorn python-multipart python-dotenv google-genai pillow yt-dlp openai-whisper torch requests "numpy<2.0"

Note: numpy<2.0 is critical to prevent conflicts with the current Whisper library.
Create a .env file in the backend folder:
GOOGLE_API_KEY=your_actual_api_key_here

Frontend Setup
Open a new terminal and set up the React client:
Initialize React app
npx create-react-app comic-frontend
cd comic-frontend
Install dependencies
npm install lucide-react
Install Tailwind CSS (v3 for stability)
npm install -D tailwindcss@3.4.1 postcss@8.4.35 autoprefixer@10.4.17

Configure Tailwind:
Ensure tailwind.config.js looks like this:
module.exports = {
content: ["./src/**/*.{js,jsx,ts,tsx}"],
theme: { extend: {} },
plugins: [],
}

Add these lines to src/index.css:
@tailwind base;
@tailwind components;
@tailwind utilities;

🏃‍♂️ Running the App
You need to run the Backend and Frontend in two separate terminals.
Terminal 1: Backend
cd backend
Make sure your virtual env is active!
python server.py

Server will start at http://localhost:8000
Terminal 2: Frontend
cd comic-frontend
npm start

App will open at http://localhost:3000
🧩 Usage Guide
Select Source: Choose Topic to type a subject manually, or YouTube to paste a video link.
Target Audience: Select the age group. This drastically changes the art style and vocabulary complexity.
Length: Choose how many pages (1-5) you want generated.
Generate: Click the button and watch the "System Log" terminal.
If using YouTube: The system will first download and listen to the video (takes ~30-60s on local machines).
Then: It generates the script and creates images panel by panel.
Export: Once finished, click Export PNG to save your comic strip.
🔧 Troubleshooting
"numpy 1.x cannot be run in NumPy 2.3.5":
Run pip install "numpy<2.0" to downgrade NumPy.
"unable to obtain file audio codec with ffprobe":
FFmpeg is missing. Install it via brew install ffmpeg (Mac) or download the binary (Windows).
"Model does not support response modalities: image":
Ensure server.py is configured to use the correct model for image generation (e.g., gemini-3-pro-image-preview or imagen-3).
📜 License
MIT License. Feel free to modify and use for your own educational projects!
