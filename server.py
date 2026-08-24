import os
import io
import re
import glob
import json 
import time 
from typing import List, Optional, Dict
from enum import Enum

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.cloud import texttospeech
from PIL import Image
import yt_dlp
import whisper
import torch

# Load environment variables
load_dotenv()

app = FastAPI(title="EduComic Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Gemini Client
try:
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
except Exception as e:
    print(f"Warning: Gemini Client failed to initialize. {e}")
    client = None

# Initialize Google Cloud TTS Client
try:
    tts_client = texttospeech.TextToSpeechClient()
except Exception as e:
    print(f"Warning: Google Cloud TTS failed to initialize. {e}")
    tts_client = None

# --- CONSTANTS ---
UPLOAD_DIR = "temp_uploads"
OUTPUT_DIR = "generated_comics"
AUDIO_DIR = "generated_audio" 
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True) 

class AgeGroup(str, Enum):
    TODDLER = "2-5"
    KID = "6-10"
    TEEN = "11+"

# --- DATA MODELS ---

class PanelData(BaseModel):
    panel_id: str
    text: str 
    duration_sec: float
    bbox_x: int = 0
    bbox_y: int = 0
    bbox_w: int = 1000
    bbox_h: int = 1000

class PageData(BaseModel):
    page_id: str
    image_url: str
    audio_url: str
    panels: List[PanelData]

class ReadAlongData(BaseModel):
    theme: str
    age_group: str
    comic_strip_url: str
    pages: List[PageData]

# --- HELPER FUNCTIONS ---

def combine_images_vertical(image_paths: List[str], output_path: str):
    """Combines images vertically into a single strip."""
    if not image_paths: return None
    try:
        images = [Image.open(path).convert("RGBA") for path in image_paths]
        widths, heights = zip(*(img.size for img in images))
        max_width = max(widths)
        total_height = sum(heights)
        
        combined_img = Image.new("RGBA", (max_width, total_height))
        y_offset = 0
        for img in images:
            combined_img.paste(img, (0, y_offset))
            y_offset += img.height
            
        combined_img.save(output_path, "PNG")
        return output_path
    except Exception as e:
        print(f"Error combining: {e}")
        return None

def is_visual_description(text: str) -> bool:
    """Check if text is a visual description rather than dialogue/narration"""
    text_lower = text.lower().strip()
    
    # Keywords that indicate visual descriptions
    visual_keywords = [
        'visual:', 'scene:', 'panel shows', 'we see', 'image of',
        'background:', 'setting:', 'shows', 'depicts', 'illustration',
        'drawing of', 'picture of', 'view of', 'close-up', 'wide shot',
        'zoom in', 'zoom out', 'angle', 'perspective', 'frame'
    ]
    
    # Check if it starts with visual indicators
    for keyword in visual_keywords:
        if text_lower.startswith(keyword):
            return True
    
    # Check if it contains visual description patterns
    if any(keyword in text_lower for keyword in ['is shown', 'is visible', 'appears in', 'stands in front']):
        return True
    
    return False

def clean_dialogue_text(text: str) -> str:
    """Remove prefixes like 'Dialogue:', 'Caption:', etc. and clean the text"""
    text = text.strip()
    
    # Remove common prefixes
    prefixes = [
        'dialogue:', 'caption:', 'narration:', 'text:', 'speech:', 
        'bubble:', 'thought:', 'voice:', 'says:', 'speaking:'
    ]
    
    text_lower = text.lower()
    for prefix in prefixes:
        if text_lower.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    
    # Remove quotes if they wrap the entire text
    if (text.startswith('"') and text.endswith('"')) or \
       (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    
    return text

def parse_comic_script_to_json(script: str) -> Dict:
    """Parses the LLM script text into a structured dictionary - extracts only titles and dialogue"""
    blocks = re.split(r"(?=\[Page\s+\d+\])", script)
    comic_data = {"theme": "", "age_group": "", "pages": []}
    page_counter = 0
    
    for block in blocks:
        block = block.strip()
        if not block: 
            continue
            
        page_match = re.match(r"\[Page\s+(\d+)\]", block)
        if not page_match: 
            continue
            
        page_counter += 1
        page_content = {
            "page_id": f"Page {page_counter}", 
            "image_url": "", 
            "audio_url": "", 
            "panels": []
        }
        
        lines = block.split('\n')
        panel_counter = 0
        
        for line in lines:
            line = line.strip()
            
            if not line or line.startswith("[Page"):
                continue
            
            # Extract title (only on page 1)
            if page_counter == 1 and line.lower().startswith("title:"):
                title_text = line[6:].strip()
                title_text = clean_dialogue_text(title_text)
                
                if title_text and not is_visual_description(title_text):
                    panel_counter += 1
                    word_count = len(title_text.split())
                    duration_sec = max(2.5, round(word_count / 2.5, 1))
                    
                    page_content["panels"].append({
                        "panel_id": f"{page_counter}-{panel_counter}", 
                        "text": title_text, 
                        "duration_sec": duration_sec,
                        "bbox_x": 0,
                        "bbox_y": 0,
                        "bbox_w": 1000,
                        "bbox_h": 1000
                    })
                    print(f"  [PARSER] Title: {title_text}")
                continue
            
            # Extract panel content
            panel_text = None
            
            # Check for arrow markers
            if line.startswith('â†’') or line.startswith('->') or line.startswith('=>'):
                if line.startswith('â†’'):
                    panel_text = line[1:].strip()
                elif line.startswith('->'):
                    panel_text = line[2:].strip()
                elif line.startswith('=>'):
                    panel_text = line[2:].strip()
            elif line.startswith('â€¢') or line.startswith('*') or line.startswith('-'):
                panel_text = line[1:].strip()
            elif ':' in line:
                # Check if it's a labeled line like "Dialogue:", "Caption:", "Visual:"
                parts = line.split(':', 1)
                label = parts[0].strip().lower()
                content = parts[1].strip() if len(parts) > 1 else ""
                
                # Only extract if it's dialogue/caption/narration (not visual descriptions)
                if label in ['dialogue', 'caption', 'narration', 'text', 'speech', 'bubble', 'thought']:
                    panel_text = content
                elif label == 'visual' or label == 'scene' or label == 'panel':
                    # Skip visual descriptions
                    continue
                elif label == 'panel' and content:
                    # Sometimes "Panel: dialogue text" format
                    panel_text = content
            
            # Clean and validate the text
            if panel_text:
                panel_text = clean_dialogue_text(panel_text)
                
                # Skip if it's a visual description or too short
                if len(panel_text) > 3 and not is_visual_description(panel_text):
                    panel_counter += 1
                    word_count = len(panel_text.split())
                    duration_sec = max(2.0, round(word_count / 3.0, 1))
                    
                    page_content["panels"].append({
                        "panel_id": f"{page_counter}-{panel_counter}", 
                        "text": panel_text, 
                        "duration_sec": duration_sec,
                        "bbox_x": 0,
                        "bbox_y": 0,
                        "bbox_w": 1000,
                        "bbox_h": 1000
                    })
                    print(f"  [PARSER] Panel {panel_counter}: {panel_text[:50]}...")
        
        # If no dialogue panels found, don't add a fallback - just leave empty
        if not page_content["panels"]:
            print(f"  [PARSER WARNING] No dialogue found for page {page_counter}")
            # Add silent panel
            page_content["panels"].append({
                "panel_id": f"{page_counter}-1", 
                "text": "", 
                "duration_sec": 1.0,
                "bbox_x": 0,
                "bbox_y": 0,
                "bbox_w": 1000,
                "bbox_h": 1000
            })
        
        print(f"[PARSER] Page {page_counter} complete: {len(page_content['panels'])} dialogue panels")
        comic_data["pages"].append(page_content)
    
    return comic_data

def detect_panels_in_image(image_path: str, num_expected_panels: int) -> List[Dict]:
    """
    Detect panel boundaries in a comic page image using contour detection.
    Returns list of bounding boxes in format: {x, y, w, h} (0-1000 scale)
    """
    try:
        import cv2
        import numpy as np
        
        # Read image
        img = cv2.imread(image_path)
        if img is None:
            print(f"Could not read image: {image_path}")
            return create_grid_panels(num_expected_panels)
        
        img_h, img_w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply adaptive thresholding to detect panel borders
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                      cv2.THRESH_BINARY_INV, 11, 2)
        
        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        panels = []
        min_area = (img_w * img_h) * 0.05  # Panel must be at least 5% of image
        max_area = (img_w * img_h) * 0.95  # Panel can't be more than 95% (avoids full image)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # Aspect ratio check - panels shouldn't be too thin
            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio < 0.2 or aspect_ratio > 5:
                continue
            
            panels.append({
                'x': int((x / img_w) * 1000),
                'y': int((y / img_h) * 1000),
                'w': int((w / img_w) * 1000),
                'h': int((h / img_h) * 1000),
                'area': area,
                'center_y': y + h // 2
            })
        
        if not panels:
            print("No panels detected, using grid layout")
            return create_grid_panels(num_expected_panels)
        
        # Sort by position (top to bottom, left to right)
        panels.sort(key=lambda p: (p['y'], p['x']))
        
        # If we found more panels than expected, keep the largest ones
        if len(panels) > num_expected_panels:
            panels.sort(key=lambda p: p['area'], reverse=True)
            panels = panels[:num_expected_panels]
            panels.sort(key=lambda p: (p['y'], p['x']))
        
        # If we found fewer panels than expected, use grid layout
        if len(panels) < num_expected_panels:
            print(f"Only found {len(panels)} panels, expected {num_expected_panels}, using grid")
            return create_grid_panels(num_expected_panels)
        
        # Remove the temporary keys
        for panel in panels:
            panel.pop('area', None)
            panel.pop('center_y', None)
        
        print(f"[PANEL DETECTION] Found {len(panels)} panels")
        return panels
        
    except ImportError:
        print("OpenCV not available, using scipy fallback")
        return detect_panels_scipy(image_path, num_expected_panels)
    except Exception as e:
        print(f"Panel detection error: {e}")
        return create_grid_panels(num_expected_panels)

def detect_panels_scipy(image_path: str, num_expected_panels: int) -> List[Dict]:
    """Fallback panel detection using scipy"""
    try:
        from PIL import Image, ImageFilter
        import numpy as np
        from scipy import ndimage
        
        img = Image.open(image_path).convert('L')
        img_array = np.array(img)
        
        # Detect edges
        edges = img_array < 200
        labeled, num_features = ndimage.label(~edges)
        
        panels = []
        img_h, img_w = img_array.shape
        min_size = min(img_h, img_w) * 0.15  # Minimum 15% of smaller dimension
        
        for i in range(1, num_features + 1):
            mask = labeled == i
            rows, cols = np.where(mask)
            
            if len(rows) < min_size or len(cols) < min_size:
                continue
                
            y_min, y_max = rows.min(), rows.max()
            x_min, x_max = cols.min(), cols.max()
            
            w = x_max - x_min
            h = y_max - y_min
            
            # Skip if too small or wrong aspect ratio
            if w < min_size or h < min_size:
                continue
            
            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio < 0.2 or aspect_ratio > 5:
                continue
            
            panels.append({
                'x': int((x_min / img_w) * 1000),
                'y': int((y_min / img_h) * 1000),
                'w': int((w / img_w) * 1000),
                'h': int((h / img_h) * 1000),
                'area': w * h
            })
        
        if len(panels) < num_expected_panels:
            return create_grid_panels(num_expected_panels)
        
        # Sort and filter
        panels.sort(key=lambda p: (p['y'], p['x']))
        panels.sort(key=lambda p: p['area'], reverse=True)
        panels = panels[:num_expected_panels]
        panels.sort(key=lambda p: (p['y'], p['x']))
        
        for panel in panels:
            panel.pop('area')
        
        return panels
        
    except Exception as e:
        print(f"Scipy detection error: {e}")
        return create_grid_panels(num_expected_panels)

def create_grid_panels(num_panels: int) -> List[Dict]:
    """Create evenly spaced grid panels as fallback"""
    print(f"[PANEL DETECTION] Creating {num_panels}-panel grid layout")
    
    if num_panels == 1:
        return [{'x': 50, 'y': 50, 'w': 900, 'h': 900}]
    elif num_panels == 2:
        return [
            {'x': 50, 'y': 50, 'w': 900, 'h': 450},
            {'x': 50, 'y': 520, 'w': 900, 'h': 450}
        ]
    elif num_panels == 3:
        return [
            {'x': 50, 'y': 50, 'w': 900, 'h': 300},
            {'x': 50, 'y': 370, 'w': 900, 'h': 300},
            {'x': 50, 'y': 690, 'w': 900, 'h': 300}
        ]
    elif num_panels == 4:
        return [
            {'x': 50, 'y': 50, 'w': 450, 'h': 450},
            {'x': 520, 'y': 50, 'w': 450, 'h': 450},
            {'x': 50, 'y': 520, 'w': 450, 'h': 450},
            {'x': 520, 'y': 520, 'w': 450, 'h': 450}
        ]
    else:
        # For 5+ panels, use 2-column layout
        cols = 2
        rows = (num_panels + 1) // 2
        panel_w = 450
        panel_h = 900 // rows
        panels = []
        
        for i in range(num_panels):
            row = i // cols
            col = i % cols
            panels.append({
                'x': 50 + col * 520,
                'y': 50 + row * (panel_h + 20),
                'w': panel_w,
                'h': panel_h - 20
            })
        return panels

def generate_audio_for_page(page_data: Dict, theme: str, age_group: str) -> str:
    """
    Generate TTS audio for a page using Google Cloud Text-to-Speech Neural voices.
    Only narrates titles and dialogue - NO visual descriptions.
    """
    try:
        if not tts_client:
            raise Exception("Google Cloud TTS client not initialized")
        
        page_num = page_data["page_id"].split()[-1]
        safe_theme = re.sub(r'\W+', '_', theme).lower()
        audio_filename = f"{safe_theme}_page_{page_num}.mp3"
        audio_path = os.path.join(AUDIO_DIR, audio_filename)
        
        # Collect only dialogue/narration text (skip visual descriptions)
        dialogue_parts = []
        for idx, panel in enumerate(page_data["panels"]):
            panel_text = panel["text"].strip()
            
            # Only add if there's actual text
            if panel_text and len(panel_text) > 0:
                dialogue_parts.append(panel_text)
                print(f"  [AUDIO] Panel {idx+1} dialogue: {panel_text[:60]}...")
        
        # Create audio text
        if dialogue_parts:
            # Add natural pauses between dialogues
            full_text = ". ".join(dialogue_parts) + "."
            print(f"[AUDIO] Full narration for page {page_num}: {full_text[:100]}...")
        else:
            # If no dialogue, create silent audio (very short)
            print(f"[AUDIO] No dialogue for page {page_num}, creating silent track")
            full_text = "."
        
        # Choose voice based on age group
        if age_group == "2-5":
            voice_name = "en-US-Neural2-F"
            speaking_rate = 0.85
            pitch = 3.0
        elif age_group == "6-10":
            voice_name = "en-US-Neural2-C"
            speaking_rate = 0.95
            pitch = 1.0
        else:  # 11+
            voice_name = "en-US-Neural2-J"
            speaking_rate = 1.0
            pitch = 0.0
        
        synthesis_input = texttospeech.SynthesisInput(text=full_text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
            pitch=pitch,
            effects_profile_id=["small-bluetooth-speaker-class-device"]
        )
        
        response = tts_client.synthesize_speech(
            input=synthesis_input, 
            voice=voice, 
            audio_config=audio_config
        )
        
        with open(audio_path, "wb") as out:
            out.write(response.audio_content)
        
        print(f"[AUDIO] Generated successfully for page {page_num}")
        return f"/audio/{audio_filename}"
        
    except Exception as e:
        print(f"[AUDIO ERROR] Google Cloud TTS failed: {e}, using gTTS fallback")
        try:
            from gtts import gTTS
            
            page_num = page_data["page_id"].split()[-1]
            safe_theme = re.sub(r'\W+', '_', theme).lower()
            audio_filename = f"{safe_theme}_page_{page_num}.mp3"
            audio_path = os.path.join(AUDIO_DIR, audio_filename)
            
            dialogue_parts = []
            for panel in page_data["panels"]:
                panel_text = panel["text"].strip()
                if panel_text and len(panel_text) > 0:
                    dialogue_parts.append(panel_text)
            
            full_text = ". ".join(dialogue_parts) + "." if dialogue_parts else "."
            
            if len(full_text) > 1:
                tts = gTTS(text=full_text, lang='en', slow=(age_group == "2-5"))
                tts.save(audio_path)
            else:
                # Create a tiny silent MP3
                import subprocess
                subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', 
                              '-t', '0.1', '-q:a', '9', '-acodec', 'libmp3lame', audio_path],
                             capture_output=True)
            
            return f"/audio/{audio_filename}"
        except Exception as e2:
            print(f"[AUDIO ERROR] gTTS failed: {e2}")
            return f"/audio/{audio_filename}"
    
def get_educational_prompt(theme: str, content: str, num_pages: int, age_group: AgeGroup) -> str:
    """Generates the prompt for the LLM to create the comic script."""
    if age_group == AgeGroup.TODDLER:
        role = "You are an illustrator for nursery rhymes and toddler picture books."
        style = "Visual Style: Bright primary colors, flat vector art, thick outlines. Cute, rounded characters (animals or soft shapes). No scary elements."
        pacing = "Pacing: Very slow, 1-2 big panels per page."
        tone = "Tone: Joyous, musical, repetitive, very simple words."
    elif age_group == AgeGroup.KID:
        role = "You are a creator of popular Saturday Morning Cartoons."
        style = "Visual Style: Vibrant, energetic, dynamic poses, expressive faces. Relatable kid characters or superheroes."
        pacing = "Pacing: Dynamic, 3-4 panels per page."
        tone = "Tone: Fun, adventurous, exciting, jokes, fun facts."
    else:
        role = "You are a professional Manga artist."
        style = "Visual Style: High-quality Manga/Anime style, detailed backgrounds, screen tones."
        pacing = "Pacing: Cinematic, 4-6 panels per page."
        tone = "Tone: Witty, cool, intellectual but accessible."

    output_format_lines = []
    for i in range(1, num_pages + 1):
        output_format_lines.append(f"[Page {i}]")
        if i == 1:
            output_format_lines.append("Title: (Catchy Title Here)")
        output_format_lines.append("Visual: (Describe what the panel shows)")
        output_format_lines.append("Dialogue: \"Character speaks here\"")
        output_format_lines.append("Visual: (Next panel description)")
        output_format_lines.append("Caption: Narrator text here")
        output_format_lines.append("")

    output_format = "\n".join(output_format_lines)

    return f"""
{role}
Create a {num_pages}-page comic script to explain: "{theme}".

ã€ Educational Contextã€‘
{content[:4000]}

ã€ Constraints for Age {age_group.value}ã€‘
- {style}
- {pacing}
- {tone}
- Page 1 must have a catchy title
- Final page must have a summary or lesson

CRITICAL FORMAT RULES:
1. Start each page with [Page N]
2. Page 1 must have "Title: Your Title Here"
3. Separate VISUAL descriptions from DIALOGUE/CAPTIONS:
   - "Visual: (what the panel shows)" - for artist reference
   - "Dialogue: (what characters say)" - will be read aloud
   - "Caption: (narrator text)" - will be read aloud
4. Keep dialogue natural and conversational
5. Do NOT prefix dialogue with "Character says:" - just write the dialogue

ã€ Example Formatã€‘
[Page 1]
Title: Adventures in Space
Visual: Wide shot of a colorful spaceship flying through stars
Dialogue: "Wow! Look at all those stars, Professor!"
Visual: Close-up of excited child pointing at window
Caption: Our journey to learn about the universe begins

[Page 2]
Visual: Inside spaceship with control panels
Dialogue: "Each star is actually a giant ball of burning gas!"
Visual: Professor pointing at holographic star
Dialogue: "Amazing! How hot are they?"

Follow this format EXACTLY. Separate visual descriptions from spoken text.
"""

def download_audio(url: str, output_path: str):
    """Downloads audio from a YouTube URL."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
        'outtmpl': output_path.replace('.mp3', ''),
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        base = output_path.replace('.mp3', '')
        possible_files = glob.glob(f"{base}*.mp3")
        if possible_files:
            os.rename(possible_files[0], output_path)
            return output_path
        return None
    except Exception as e:
        print(f"DL Error: {e}")
        return None

def transcribe_audio_local(audio_path: str):
    """Transcribes local audio file using Whisper."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Whisper ({device} mode)...")
    model = whisper.load_model('base', device=device) 
    result = model.transcribe(audio_path)
    return result['text']

# --- API ENDPOINTS ---

class ComicRequest(BaseModel):
    theme: str
    youtube_url: Optional[str] = None
    age_group: AgeGroup
    num_pages: int = 4

@app.get("/audio/{filename}")
async def get_audio_file(filename: str):
    audio_path = os.path.join(AUDIO_DIR, filename)
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(audio_path, media_type="audio/mp3")

@app.get("/generated_comics/{filename}")
async def get_comic_file(filename: str):
    comic_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(comic_path):
        raise HTTPException(status_code=404, detail="Comic file not found")
    return FileResponse(comic_path, media_type="image/png")

@app.post("/process-content")
async def process_content(request: ComicRequest):
    if not client:
        raise HTTPException(status_code=500, detail="Gemini client not initialized.")
        
    content_context = ""
    if request.youtube_url:
        print(f"Processing Video: {request.youtube_url}")
        file_id = re.sub(r'[^\w\s-]', '', request.youtube_url).strip().replace(' ', '_')[-16:]
        audio_path = os.path.join(UPLOAD_DIR, f"{file_id}.mp3")
        
        if not os.path.exists(audio_path):
            downloaded_path = download_audio(request.youtube_url, audio_path)
            if not downloaded_path:
                raise HTTPException(status_code=400, detail="Failed to download audio")
            audio_path = downloaded_path
            
        try:
            transcript = transcribe_audio_local(audio_path)
            summary_prompt = f"Extract the core educational concepts from this transcript suitable for a {request.age_group.value} year old:\n\n{transcript[:10000]}"
            summary_resp = client.models.generate_content(
                model="gemini-3-pro-preview", 
                contents=summary_prompt
            )
            content_context = summary_resp.text
        except Exception as e:
            print(f"Transcription/Summary error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        content_context = "General topic explanation."

    return {"context": content_context}

@app.post("/generate-comic-with-audio")
async def generate_comic_with_audio_endpoint(
    theme: str = Form(...),
    context: str = Form(...),
    age_group: AgeGroup = Form(...),
    num_pages: int = Form(...)
):
    if not client:
        raise HTTPException(status_code=500, detail="Gemini client not initialized.")
        
    try:
        # 1. Generate Plot
        print("=" * 50)
        print("Step 1: Generating Plot...")
        print("=" * 50)
        prompt = get_educational_prompt(theme, context, num_pages, age_group)
        
        plot_response = client.models.generate_content(
            model="gemini-3-pro-preview", 
            contents=prompt
        )
        plot_text = plot_response.text
        print("[PLOT GENERATED]")
        print(plot_text)
        print("=" * 50)
        
        # 2. Parse Plot (extract only dialogue/captions, skip visuals)
        print("Step 2: Parsing Plot...")
        comic_data = parse_comic_script_to_json(plot_text) 
        comic_data["theme"] = theme
        comic_data["age_group"] = age_group.value
        print(f"[PARSE COMPLETE] {len(comic_data['pages'])} pages parsed")
        print("=" * 50)

        # 3. Generate Images
        print("Step 3: Starting Image Generation Session...")
        
        chat = client.chats.create(
            model="gemini-3-pro-image-preview",
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )
        
        image_files = []
        generated_pages_pil = []
        
        for i, page_data in enumerate(comic_data["pages"]):
            page_num = i + 1
            page_start_marker = f"[Page {page_num}]"
            page_end_marker = f"[Page {page_num + 1}]" if page_num < num_pages else "END_OF_SCRIPT"
            
            start_index = plot_text.find(page_start_marker)
            end_index = plot_text.find(page_end_marker, start_index + len(page_start_marker))
            
            if start_index == -1: continue

            page_prompt = plot_text[start_index:end_index].strip() if end_index != -1 else plot_text[start_index:].strip()
            
            print(f"Generating Image for Page {page_num}/{num_pages}...")
            
            message_parts = [page_prompt]
            if generated_pages_pil:
                message_parts.append(generated_pages_pil[-1])
            
            try:
                response = chat.send_message(message_parts)
                
                if response.parts:
                    for part in response.parts:
                        if part.inline_data:
                            img = Image.open(io.BytesIO(part.inline_data.data))
                            
                            fname = f"comic_{theme[:5].replace(' ', '_')}_{page_num}.png"
                            fpath = os.path.join(OUTPUT_DIR, fname)
                            img.save(fpath)
                            
                            image_files.append(fpath)
                            generated_pages_pil.append(img)
                            
                            page_data["image_url"] = f"/generated_comics/{fname}" 
                            
                            # DETECT PANELS IN THIS IMAGE
                            num_panels = len(page_data["panels"])
                            detected_panels = detect_panels_in_image(fpath, num_panels)
                            
                            # Update panel bboxes with detected coordinates
                            for p_idx, panel in enumerate(page_data["panels"]):
                                if p_idx < len(detected_panels):
                                    panel["bbox_x"] = detected_panels[p_idx]['x']
                                    panel["bbox_y"] = detected_panels[p_idx]['y']
                                    panel["bbox_w"] = detected_panels[p_idx]['w']
                                    panel["bbox_h"] = detected_panels[p_idx]['h']
                                    print(f"  Panel {p_idx+1} bbox: x={panel['bbox_x']}, y={panel['bbox_y']}, w={panel['bbox_w']}, h={panel['bbox_h']}")
                                
                            break
            except Exception as e:
                print(f"Error on page {page_num}: {e}")
                continue

        print("=" * 50)
        # 4. Generate Audio for each page (dialogue only)
        print("Step 4: Generating Audio with Google Cloud TTS...")
        for i, page_data in enumerate(comic_data["pages"]):
            print(f"Processing audio for page {i+1}...")
            audio_url = generate_audio_for_page(page_data, theme, age_group.value)
            page_data["audio_url"] = audio_url
        print("=" * 50)

        # 5. Combine Images
        print("Step 5: Combining images...")
        if not image_files:
            raise HTTPException(status_code=500, detail="Failed to generate any images.")

        final_filename = f"final_{theme[:10].replace(' ', '_')}_{age_group.value}.png"
        final_path = os.path.join(OUTPUT_DIR, final_filename)
        combine_images_vertical(image_files, final_path)
        
        # 6. Return structured data
        print("Step 6: Returning data...")
        print("=" * 50)
        
        read_along_result = ReadAlongData(
            theme=theme,
            age_group=age_group.value,
            comic_strip_url=f"/generated_comics/{final_filename}",
            pages=[PageData(**page) for page in comic_data["pages"]]
        )
        
        return JSONResponse(content={
            "comic_strip_url": read_along_result.comic_strip_url,
            "read_along_data": read_along_result.dict()
        })

    except Exception as e:
        print(f"Critical Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)