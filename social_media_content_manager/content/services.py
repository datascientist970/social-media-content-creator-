import os
import subprocess
import warnings
import re
import base64
import json
import time
import random
import hashlib
import difflib
import threading
import concurrent.futures
import requests
from PIL import Image
from django.conf import settings
from datetime import timedelta

warnings.filterwarnings('ignore')
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

def debug_print(msg):
    print(f"[DEBUG] {msg}")

_cache = {}
_cache_lock = threading.Lock()

def get_cache_key(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read(1024*1024)).hexdigest()
        return file_hash
    return None


class VideoFrameExtractor:
    @staticmethod
    def extract_multiple_frames(video_path, num_frames=3):
        frames = []
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                return []
            interval = max(1, total_frames // (num_frames + 1))
            frame_indices = [interval * i for i in range(1, num_frames + 1) if interval * i < total_frames]
            for idx, frame_num in enumerate(frame_indices[:num_frames]):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if ret:
                    frame_path = video_path.replace('.mp4', f'_frame_{idx}.jpg')
                    cv2.imwrite(frame_path, frame)
                    frames.append(frame_path)
            cap.release()
            return frames
        except Exception as e:
            debug_print(f"Frame extraction error: {e}")
            return []


class SceneDetector:
    @staticmethod
    def detect_scenes(video_path, threshold=30):
        try:
            from scenedetect import VideoManager, SceneManager
            from scenedetect.detectors import ContentDetector
            video_manager = VideoManager([video_path])
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=threshold))
            video_manager.set_downscale_factor()
            video_manager.start()
            scene_manager.detect_scenes(frame_source=video_manager)
            scenes = scene_manager.get_scene_list()
            video_manager.release()
            scene_times = [(scene[0].get_seconds(), scene[1].get_seconds()) for scene in scenes]
            debug_print(f"Detected {len(scene_times)} scenes")
            return scene_times
        except:
            return []
    
    @staticmethod
    def extract_frames_at_timestamps(video_path, timestamps):
        frames = []
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            for ts in timestamps:
                cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
                ret, frame = cap.read()
                if ret:
                    frame_path = video_path.replace('.mp4', f'_frame_{ts:.1f}s.jpg')
                    cv2.imwrite(frame_path, frame)
                    frames.append((frame_path, ts))
            cap.release()
            return frames
        except:
            return []


class AudioProcessor:
    @staticmethod
    def convert_to_wav(input_path, output_path=None):
        if not output_path:
            output_path = input_path.replace('.mp3', '_converted.wav')
        command = ['ffmpeg', '-i', input_path, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', '-y', output_path]
        try:
            subprocess.run(command, capture_output=True, check=True, shell=True, timeout=30)
            return output_path
        except:
            return input_path
    
    @staticmethod
    def clean_audio(input_path, output_path=None):
        if not output_path:
            output_path = input_path.replace('.mp3', '_cleaned.mp3')
        command = ['ffmpeg', '-i', input_path, '-af', 'highpass=f=200, lowpass=f=3000, afftdn, volume=2', '-y', output_path]
        try:
            subprocess.run(command, capture_output=True, check=True, shell=True, timeout=30)
            return output_path
        except:
            return input_path


class TranscriptMerger:
    @staticmethod
    def merge_transcripts(whisper_text, google_text):
        if not whisper_text and not google_text:
            return "", []
        if not whisper_text:
            return google_text, []
        if not google_text:
            return whisper_text, []
        whisper_words = whisper_text.split()
        google_words = google_text.split()
        matcher = difflib.SequenceMatcher(None, whisper_words, google_words)
        merged_words = []
        conflicts = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                merged_words.extend(whisper_words[i1:i2])
            elif tag == 'replace':
                whisper_part = ' '.join(whisper_words[i1:i2])
                google_part = ' '.join(google_words[j1:j2])
                conflicts.append(f"'{whisper_part}' vs '{google_part}'")
                merged_words.extend(whisper_words[i1:i2])
            elif tag == 'delete':
                merged_words.extend(whisper_words[i1:i2])
            elif tag == 'insert':
                merged_words.extend(google_words[j1:j2])
        return ' '.join(merged_words), conflicts


class GeminiVisionService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.last_request_time = 0
        self.request_count = 0
        debug_print(f"Gemini Vision service ready")
    
    def _wait_for_rate_limit(self):
        current_time = time.time()
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        if self.request_count >= 14:
            wait_time = 5 + random.random() * 2
            time.sleep(wait_time)
            self.request_count = 0
            self.last_request_time = time.time()
        self.request_count += 1
    
    def _call_with_retry(self, url, data, max_retries=3):
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=30)
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:
                    time.sleep((2 ** attempt) + random.random())
                else:
                    return response
            except:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        return None
    
    def analyze_image_with_gemini(self, image_path):
        self._wait_for_rate_limit()
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            mime_type = 'image/jpeg' if not image_path.endswith('.png') else 'image/png'
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            data = {
                "contents": [{
                    "parts": [
                        {"text": "Describe this image in ENGLISH in 2-3 sentences."},
                        {"inline_data": {"mime_type": mime_type, "data": image_base64}}
                    ]
                }],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 300}
            }
            response = self._call_with_retry(url, data)
            if response and response.status_code == 200:
                result = response.json()
                candidates = result.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if parts:
                        return parts[0].get('text', '')
            return None
        except:
            return None
    
    def extract_visual_context_structured(self, frame_paths, timestamps=None):
        if not frame_paths:
            return None
        self._wait_for_rate_limit()
        try:
            parts = [{"text": "Analyze these frames. Return JSON: {\"objects\":[],\"actions\":[],\"products\":[],\"confidence\":85}"}]
            for frame_path in frame_paths[:3]:
                with open(frame_path, 'rb') as f:
                    image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                mime_type = 'image/jpeg' if not frame_path.endswith('.png') else 'image/png'
                parts.append({"inline_data": {"mime_type": mime_type, "data": image_base64}})
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            data = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800}}
            response = self._call_with_retry(url, data)
            if response and response.status_code == 200:
                result = response.json()
                candidates = result.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if parts:
                        text = parts[0].get('text', '')
                        json_match = re.search(r'\{.*\}', text, re.DOTALL)
                        if json_match:
                            return json.loads(json_match.group())
            return None
        except:
            return None


class WhisperService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self.model = None
        debug_print("Whisper service ready")
    
    def _load_model(self):
        try:
            import whisper
            self.model = whisper.load_model("base", device="cpu")
            return True
        except:
            return False
    
    def extract_audio(self, video_path):
        audio_path = video_path.replace('.mp4', '_audio.mp3')
        command = ['ffmpeg', '-i', video_path, '-q:a', '0', '-map', 'a', audio_path, '-y']
        try:
            subprocess.run(command, capture_output=True, check=True, shell=True, timeout=30)
            return audio_path if os.path.exists(audio_path) else None
        except:
            return None
    
    def transcribe_with_timestamps(self, media_path, is_video=False):
        if self.model is None:
            if not self._load_model():
                return "", 0, []
        try:
            if is_video:
                audio_path = self.extract_audio(media_path)
                if not audio_path:
                    return "", 0, []
            else:
                audio_path = media_path
            result = self.model.transcribe(audio_path, word_timestamps=True)
            transcript = result["text"]
            raw_confidence = result.get("avg_logprob", -1)
            confidence = max(0, min(100, (raw_confidence + 2) * 50)) if raw_confidence < 0 else 50
            segments = [{'start': seg.get('start', 0), 'end': seg.get('end', 0), 'text': seg.get('text', ''), 'confidence': max(0, min(100, (seg.get('avg_logprob', -1) + 2) * 50))} for seg in result.get("segments", [])]
            if is_video and audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            return transcript, confidence, segments
        except:
            return "", 0, []


class GoogleSTTService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        debug_print("Google STT service ready")
    
    def transcribe_with_confidence(self, audio_path):
        try:
            import speech_recognition as sr
            wav_path = AudioProcessor.convert_to_wav(audio_path)
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio = r.record(source)
            transcript = r.recognize_google(audio)
            confidence = min(85, max(40, len(transcript) / 200 * 100)) if transcript else 0
            if wav_path != audio_path and os.path.exists(wav_path):
                os.remove(wav_path)
            return transcript, confidence
        except:
            return "", 0


class TranscriptCorrectionService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        debug_print("Transcript Correction Service ready")
    
    def _chunk_transcript(self, transcript, max_chars=1500):
        if len(transcript) <= max_chars:
            return [transcript]
        chunks = []
        sentences = re.split(r'(?<=[.!?])\s+', transcript)
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_chars:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks
    
    def _calculate_final_confidence(self, whisper_conf, google_conf, visual_conf):
        final_conf = (whisper_conf * 0.5 + google_conf * 0.2 + visual_conf * 0.3)
        if whisper_conf < 40 or google_conf < 40:
            final_conf *= 0.7
        return min(100, max(0, final_conf))
    
    def _call_with_retry(self, prompt, max_retries=3):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        data = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000}}
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=60)
                if response.status_code == 200:
                    result = response.json()
                    candidates = result.get('candidates', [])
                    if candidates:
                        parts = candidates[0].get('content', {}).get('parts', [])
                        if parts:
                            return parts[0].get('text', '')
                    return None
                elif response.status_code == 429:
                    time.sleep((2 ** attempt) + random.random())
                else:
                    return None
            except:
                pass
        return None
    
    def correct_transcript(self, whisper_transcript, whisper_confidence, whisper_segments,
                          google_transcript, google_confidence, visual_context,
                          merged_transcript=None, conflicts=None):
        if not whisper_transcript and not google_transcript:
            return None
        visual_conf = visual_context.get('confidence', 0) if visual_context else 0
        final_confidence = self._calculate_final_confidence(whisper_confidence, google_confidence, visual_conf)
        primary_text = merged_transcript if merged_transcript else whisper_transcript
        if not primary_text:
            primary_text = google_transcript
        chunks = self._chunk_transcript(primary_text, max_chars=1500)
        corrected_chunks = []
        for chunk in chunks:
            prompt = f"""Clean this transcript. Return JSON: {{"corrected_transcript":"clean text","main_topic":"topic","key_points":[],"products_services":"","confidence_score":{final_confidence:.0f}}}"
TRANSCRIPT: {chunk}"""
            response = self._call_with_retry(prompt)
            if response:
                try:
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        corrected_chunks.append(json.loads(json_match.group()))
                except:
                    pass
        if corrected_chunks:
            merged = corrected_chunks[0]
            if len(corrected_chunks) > 1:
                merged['corrected_transcript'] = " ".join([c['corrected_transcript'] for c in corrected_chunks])
            merged['confidence_score'] = final_confidence
            return merged
        return None


class ContentGeneratorService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        debug_print(f"Content generator ready with model: {self.model}")
    
    def _call_gemini_api(self, prompt):
        """Direct Gemini API call with error details"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4000,  # Increased for more content
                "topP": 0.95
            }
        }
        
        try:
            debug_print("Calling Gemini API...")
            response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=90)
            debug_print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                candidates = result.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if parts:
                        response_text = parts[0].get('text', '')
                        debug_print(f"Response received, length: {len(response_text)}")
                        return response_text
                debug_print("No candidates in response")
                return None
            elif response.status_code == 403:
                debug_print(f"ERROR: Invalid API key. Status 403")
                return None
            elif response.status_code == 429:
                debug_print(f"ERROR: Rate limit exceeded. Status 429")
                return None
            else:
                debug_print(f"ERROR: Unknown error. Status {response.status_code}")
                return None
        except Exception as e:
            debug_print(f"ERROR: Exception - {e}")
            return None
    
    def generate_content(self, data, content_type="video", user_text=""):
        debug_print(f"Generating content for type: {content_type}")
        
        # Get content source
        if content_type == "image":
            content_source = data.get('description', '') if data else user_text
            if not content_source:
                return {'error': 'No image description available', 'code': 'NO_CONTENT'}
        elif content_type == "text":
            content_source = user_text if user_text else data.get('description', '') if data else ''
            if not content_source:
                return {'error': 'No text content available', 'code': 'NO_CONTENT'}
        else:  # video
            content_source = data.get('corrected_transcript', '') if data else ''
            if not content_source:
                content_source = user_text
            if not content_source:
                return {'error': 'No video transcript available', 'code': 'NO_CONTENT'}
        
        debug_print(f"Content source length: {len(content_source)}")
        
        # Force complete response prompt
        prompt = f"""Based on the following content, create COMPLETE social media posts for ALL platforms in ENGLISH ONLY.

CONTENT:
{content_source[:1500]}

CRITICAL: You MUST provide content for EVERY platform below. Do NOT skip any.

Write in EXACTLY this format (copy these headers exactly):

YOUTUBE_TITLE: [your title here]
YOUTUBE_DESCRIPTION: [your description here]
YOUTUBE_TAGS: [tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8, tag9, tag10]

INSTAGRAM_CAPTION: [your caption here]
INSTAGRAM_HASHTAGS: [#tag1 #tag2 #tag3 #tag4 #tag5 #tag6 #tag7 #tag8 #tag9 #tag10 #tag11 #tag12 #tag13 #tag14 #tag15 #tag16 #tag17 #tag18 #tag19 #tag20]

FACEBOOK_POST: [your post here]
FACEBOOK_HASHTAGS: [#tag1, #tag2, #tag3, #tag4, #tag5, #tag6, #tag7, #tag8, #tag9, #tag10]

LINKEDIN_POST: [your post here]
LINKEDIN_HASHTAGS: [#tag1, #tag2, #tag3, #tag4, #tag5, #tag6, #tag7, #tag8]

TWITTER_TWEET: [your tweet here]
TWITTER_HASHTAGS: [#tag1, #tag2, #tag3, #tag4, #tag5]

TIKTOK_CAPTION: [your caption here]
TIKTOK_HASHTAGS: [#tag1 #tag2 #tag3 #tag4 #tag5 #tag6 #tag7 #tag8 #tag9 #tag10]

PINTEREST_TITLE: [your title here]
PINTEREST_DESCRIPTION: [your description here]
PINTEREST_HASHTAGS: [#tag1 #tag2 #tag3 #tag4 #tag5 #tag6 #tag7 #tag8 #tag9 #tag10]

Make all content engaging, relevant, and ready to post. Complete ALL sections."""
        
        response = self._call_gemini_api(prompt)
        
        if response:
            debug_print(f"Got Gemini response, length: {len(response)}")
            parsed = self._parse_response_complete(response)
            
            # Verify all platforms have content
            missing_platforms = []
            for platform in ['instagram', 'facebook', 'linkedin', 'twitter', 'tiktok', 'pinterest']:
                if platform == 'instagram':
                    if not parsed[platform].get('caption') and not parsed[platform].get('hashtags'):
                        missing_platforms.append(platform)
                elif platform == 'facebook':
                    if not parsed[platform].get('post') and not parsed[platform].get('hashtags'):
                        missing_platforms.append(platform)
                elif platform == 'linkedin':
                    if not parsed[platform].get('post') and not parsed[platform].get('hashtags'):
                        missing_platforms.append(platform)
                elif platform == 'twitter':
                    if not parsed[platform].get('tweet') and not parsed[platform].get('hashtags'):
                        missing_platforms.append(platform)
                elif platform == 'tiktok':
                    if not parsed[platform].get('caption') and not parsed[platform].get('hashtags'):
                        missing_platforms.append(platform)
                elif platform == 'pinterest':
                    if not parsed[platform].get('title') and not parsed[platform].get('description') and not parsed[platform].get('hashtags'):
                        missing_platforms.append(platform)
            
            if missing_platforms:
                debug_print(f"Missing platforms: {missing_platforms}")
                # Try to extract from response again
                parsed = self._extract_all_sections(response, parsed)
            
            return parsed
        
        debug_print("No valid response from Gemini API")
        return {'error': 'Gemini API failed. Please check your API key.', 'code': 'GEMINI_FAILED'}
    
    def _parse_response_complete(self, response):
        """Complete parsing for all platforms"""
        content = {
            'youtube': {'title': '', 'description': '', 'tags': ''},
            'instagram': {'caption': '', 'hashtags': ''},
            'facebook': {'post': '', 'hashtags': ''},
            'linkedin': {'post': '', 'hashtags': ''},
            'twitter': {'tweet': '', 'hashtags': ''},
            'tiktok': {'caption': '', 'hashtags': ''},
            'pinterest': {'title': '', 'description': '', 'hashtags': ''}
        }
        
        # Split into sections
        sections = re.split(r'\n(?=[A-Z_]+:)', response)
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            # YouTube
            if 'YOUTUBE_TITLE:' in section:
                match = re.search(r'YOUTUBE_TITLE:\s*(.+?)(?=\nYOUTUBE_DESCRIPTION:|$)', section, re.DOTALL)
                if match:
                    content['youtube']['title'] = match.group(1).strip()
            if 'YOUTUBE_DESCRIPTION:' in section:
                match = re.search(r'YOUTUBE_DESCRIPTION:\s*(.+?)(?=\nYOUTUBE_TAGS:|$)', section, re.DOTALL)
                if match:
                    content['youtube']['description'] = match.group(1).strip()
            if 'YOUTUBE_TAGS:' in section:
                match = re.search(r'YOUTUBE_TAGS:\s*(.+?)(?=\nINSTAGRAM_CAPTION:|$)', section, re.DOTALL)
                if match:
                    content['youtube']['tags'] = match.group(1).strip()
            
            # Instagram
            if 'INSTAGRAM_CAPTION:' in section:
                match = re.search(r'INSTAGRAM_CAPTION:\s*(.+?)(?=\nINSTAGRAM_HASHTAGS:|$)', section, re.DOTALL)
                if match:
                    content['instagram']['caption'] = match.group(1).strip()
            if 'INSTAGRAM_HASHTAGS:' in section:
                match = re.search(r'INSTAGRAM_HASHTAGS:\s*(.+?)(?=\nFACEBOOK_POST:|$)', section, re.DOTALL)
                if match:
                    content['instagram']['hashtags'] = match.group(1).strip()
            
            # Facebook
            if 'FACEBOOK_POST:' in section:
                match = re.search(r'FACEBOOK_POST:\s*(.+?)(?=\nFACEBOOK_HASHTAGS:|$)', section, re.DOTALL)
                if match:
                    content['facebook']['post'] = match.group(1).strip()
            if 'FACEBOOK_HASHTAGS:' in section:
                match = re.search(r'FACEBOOK_HASHTAGS:\s*(.+?)(?=\nLINKEDIN_POST:|$)', section, re.DOTALL)
                if match:
                    content['facebook']['hashtags'] = match.group(1).strip()
            
            # LinkedIn
            if 'LINKEDIN_POST:' in section:
                match = re.search(r'LINKEDIN_POST:\s*(.+?)(?=\nLINKEDIN_HASHTAGS:|$)', section, re.DOTALL)
                if match:
                    content['linkedin']['post'] = match.group(1).strip()
            if 'LINKEDIN_HASHTAGS:' in section:
                match = re.search(r'LINKEDIN_HASHTAGS:\s*(.+?)(?=\nTWITTER_TWEET:|$)', section, re.DOTALL)
                if match:
                    content['linkedin']['hashtags'] = match.group(1).strip()
            
            # Twitter
            if 'TWITTER_TWEET:' in section:
                match = re.search(r'TWITTER_TWEET:\s*(.+?)(?=\nTWITTER_HASHTAGS:|$)', section, re.DOTALL)
                if match:
                    content['twitter']['tweet'] = match.group(1).strip()
            if 'TWITTER_HASHTAGS:' in section:
                match = re.search(r'TWITTER_HASHTAGS:\s*(.+?)(?=\nTIKTOK_CAPTION:|$)', section, re.DOTALL)
                if match:
                    content['twitter']['hashtags'] = match.group(1).strip()
            
            # TikTok
            if 'TIKTOK_CAPTION:' in section:
                match = re.search(r'TIKTOK_CAPTION:\s*(.+?)(?=\nTIKTOK_HASHTAGS:|$)', section, re.DOTALL)
                if match:
                    content['tiktok']['caption'] = match.group(1).strip()
            if 'TIKTOK_HASHTAGS:' in section:
                match = re.search(r'TIKTOK_HASHTAGS:\s*(.+?)(?=\nPINTEREST_TITLE:|$)', section, re.DOTALL)
                if match:
                    content['tiktok']['hashtags'] = match.group(1).strip()
            
            # Pinterest
            if 'PINTEREST_TITLE:' in section:
                match = re.search(r'PINTEREST_TITLE:\s*(.+?)(?=\nPINTEREST_DESCRIPTION:|$)', section, re.DOTALL)
                if match:
                    content['pinterest']['title'] = match.group(1).strip()
            if 'PINTEREST_DESCRIPTION:' in section:
                match = re.search(r'PINTEREST_DESCRIPTION:\s*(.+?)(?=\nPINTEREST_HASHTAGS:|$)', section, re.DOTALL)
                if match:
                    content['pinterest']['description'] = match.group(1).strip()
            if 'PINTEREST_HASHTAGS:' in section:
                match = re.search(r'PINTEREST_HASHTAGS:\s*(.+?)(?=\n|$)', section, re.DOTALL)
                if match:
                    content['pinterest']['hashtags'] = match.group(1).strip()
        
        # Clean up all fields
        for platform in content:
            for field in content[platform]:
                if content[platform][field]:
                    # Remove markdown and clean
                    content[platform][field] = re.sub(r'\*\*', '', content[platform][field])
                    content[platform][field] = re.sub(r'\[|\]', '', content[platform][field])
                    content[platform][field] = content[platform][field].strip()
        
        return content
    
    def _extract_all_sections(self, response, current_content):
        """Extract any missing sections directly from response"""
        lines = response.split('\n')
        current_platform = None
        current_field = None
        buffer = []
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Detect platforms
            if 'instagram_caption' in line_lower or 'instagram caption' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'instagram'
                current_field = 'caption'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'instagram_hashtags' in line_lower or 'instagram hashtags' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'instagram'
                current_field = 'hashtags'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'facebook_post' in line_lower or 'facebook post' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'facebook'
                current_field = 'post'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'facebook_hashtags' in line_lower or 'facebook hashtags' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'facebook'
                current_field = 'hashtags'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'linkedin_post' in line_lower or 'linkedin post' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'linkedin'
                current_field = 'post'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'linkedin_hashtags' in line_lower or 'linkedin hashtags' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'linkedin'
                current_field = 'hashtags'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'twitter_tweet' in line_lower or 'twitter tweet' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'twitter'
                current_field = 'tweet'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'twitter_hashtags' in line_lower or 'twitter hashtags' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'twitter'
                current_field = 'hashtags'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'tiktok_caption' in line_lower or 'tiktok caption' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'tiktok'
                current_field = 'caption'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'tiktok_hashtags' in line_lower or 'tiktok hashtags' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'tiktok'
                current_field = 'hashtags'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'pinterest_title' in line_lower or 'pinterest title' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'pinterest'
                current_field = 'title'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'pinterest_description' in line_lower or 'pinterest description' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'pinterest'
                current_field = 'description'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif 'pinterest_hashtags' in line_lower or 'pinterest hashtags' in line_lower:
                if current_platform and current_field and buffer:
                    self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
                current_platform = 'pinterest'
                current_field = 'hashtags'
                buffer = [re.sub(r'^[^:]*:', '', line).strip()]
            elif current_platform and current_field:
                buffer.append(line)
        
        # Save last buffer
        if current_platform and current_field and buffer:
            self._save_to_content(current_platform, current_field, ' '.join(buffer), current_content)
        
        return current_content
    
    def _save_to_content(self, platform, field, value, content):
        """Save extracted value to content dictionary"""
        value = value.strip()
        if not value:
            return
        value = re.sub(r'\*\*', '', value)
        value = re.sub(r'\[|\]', '', value)
        value = value.strip()
        if value:
            content[platform][field] = value
            debug_print(f"Extracted {platform}.{field}: {value[:50]}...")