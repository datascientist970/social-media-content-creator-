import os
import subprocess
import warnings
import re
import base64
import json
import time
import random
import requests
from PIL import Image
from django.conf import settings

warnings.filterwarnings('ignore')
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

def debug_print(msg):
    print(f"[DEBUG] {msg}")

class GeminiVisionService:
    """Service for analyzing images using Gemini Vision API"""
    
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
        debug_print(f"Gemini Vision service ready (model: {self.model})")
    
    def _wait_for_rate_limit(self):
        """Wait if we're approaching rate limits"""
        current_time = time.time()
        
        if current_time - self.last_request_time > 60:
            self.request_count = 0
            self.last_request_time = current_time
        
        if self.request_count >= 14:
            wait_time = 5 + random.random() * 2
            debug_print(f"Rate limit approaching, waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            self.request_count = 0
            self.last_request_time = time.time()
        
        self.request_count += 1
    
    def _resize_image_if_needed(self, image_path):
        """Resize image if too large to avoid 400 errors"""
        try:
            with Image.open(image_path) as img:
                if img.width > 1200 or img.height > 1200:
                    ratio = min(1200 / img.width, 1200 / img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    temp_resized = image_path + '_resized.jpg'
                    img.save(temp_resized, quality=85)
                    debug_print(f"Resized image from {img.width}x{img.height} to {new_size}")
                    return temp_resized
            return image_path
        except Exception as e:
            debug_print(f"Resize error: {e}")
            return image_path
    
    def analyze_image_with_gemini(self, image_path, retry_count=0):
        """Use Gemini Vision to analyze image with retry logic"""
        
        self._wait_for_rate_limit()
        
        temp_resized = None
        
        try:
            if not os.path.exists(image_path):
                debug_print(f"Image file not found: {image_path}")
                return {'error': 'File not found', 'code': 'FILE_NOT_FOUND'}
            
            actual_path = self._resize_image_if_needed(image_path)
            if actual_path != image_path:
                temp_resized = actual_path
            
            with open(actual_path, 'rb') as f:
                image_data = f.read()
            
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            if actual_path.endswith('.png'):
                mime_type = 'image/png'
            else:
                mime_type = 'image/jpeg'
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            
            data = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": "Describe this image in 2-3 sentences. What do you see?"
                            },
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": image_base64
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 200
                }
            }
            
            debug_print(f"Calling Gemini Vision API...")
            response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=60)
            
            if temp_resized and os.path.exists(temp_resized):
                os.remove(temp_resized)
            
            if response.status_code == 429:
                debug_print(f"Rate limit (429) hit")
                return {
                    'error': 'Rate limit exceeded. Please wait 1 minute before trying again.',
                    'code': 'RATE_LIMIT',
                    'retry_after': 60
                }
                
            if response.status_code == 400:
                debug_print(f"Bad request (400)")
                return {
                    'error': 'Invalid request. Please try a different image.',
                    'code': 'BAD_REQUEST'
                }
                
            if response.status_code == 403:
                debug_print(f"Authentication error (403)")
                return {
                    'error': 'API key invalid or expired. Please check your Gemini API key.',
                    'code': 'AUTH_ERROR'
                }
                
            if response.status_code == 503:
                debug_print(f"Service unavailable (503)")
                return {
                    'error': 'Gemini API service is temporarily unavailable. Please try again later.',
                    'code': 'SERVICE_UNAVAILABLE'
                }
                
            if response.status_code != 200:
                debug_print(f"API error: {response.status_code}")
                return {
                    'error': f'API error (Status {response.status_code}). Please try again later.',
                    'code': 'API_ERROR'
                }
                
            result = response.json()
            candidates = result.get('candidates', [])
            if candidates:
                content = candidates[0].get('content', {})
                parts = content.get('parts', [])
                if parts:
                    description = parts[0].get('text', '')
                    debug_print(f"Description: {description[:100]}")
                    return {
                        'description': description,
                        'theme': self._extract_theme(description),
                        'is_islamic': 'ramadan' in description.lower() or 'quran' in description.lower(),
                        'success': True
                    }
            
            return {
                'error': 'No analysis result from Gemini API',
                'code': 'NO_RESULT'
            }
            
        except requests.exceptions.Timeout:
            debug_print(f"Timeout error")
            return {
                'error': 'Request timed out. Please try again.',
                'code': 'TIMEOUT'
            }
        except requests.exceptions.ConnectionError:
            debug_print(f"Connection error")
            return {
                'error': 'Network connection error. Please check your internet.',
                'code': 'CONNECTION_ERROR'
            }
        except Exception as e:
            debug_print(f"Error: {e}")
            return {
                'error': f'Unexpected error: {str(e)}',
                'code': 'UNKNOWN_ERROR'
            }
    
    def _extract_theme(self, description):
        """Extract theme from description"""
        desc_lower = description.lower()
        if 'strawberry' in desc_lower or 'fruit' in desc_lower or 'food' in desc_lower:
            return 'food'
        elif 'digital' in desc_lower or 'marketing' in desc_lower:
            return 'digital_marketing'
        elif 'nature' in desc_lower or 'landscape' in desc_lower:
            return 'nature'
        elif 'business' in desc_lower:
            return 'business'
        elif 'ramadan' in desc_lower or 'quran' in desc_lower:
            return 'islamic'
        else:
            return 'general'


class WhisperService:
    """Service for audio/video transcription"""
    
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
            debug_print("Loading Whisper model...")
            self.model = whisper.load_model("base")
            debug_print("Whisper loaded successfully")
            return True
        except Exception as e:
            debug_print(f"Whisper load error: {e}")
            return False
    
    def extract_audio(self, video_path):
        audio_path = video_path.replace('.mp4', '_audio.mp3').replace('.mov', '_audio.mp3')
        command = ['ffmpeg', '-i', video_path, '-q:a', '0', '-map', 'a', audio_path, '-y']
        try:
            debug_print(f"Extracting audio...")
            subprocess.run(command, capture_output=True, check=True, shell=True, timeout=30)
            if os.path.exists(audio_path):
                return audio_path
            return None
        except:
            return None
    
    def transcribe(self, media_path, is_video=False):
        if self.model is None:
            if not self._load_model():
                return ""
        
        try:
            if is_video:
                audio_path = self.extract_audio(media_path)
                if not audio_path:
                    return ""
            else:
                audio_path = media_path
            
            result = self.model.transcribe(audio_path)
            transcript = result["text"]
            
            if is_video and audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            
            return transcript
        except:
            return ""


class VideoFrameExtractor:
    @staticmethod
    def extract_first_frame(video_path):
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            ret, frame = cap.read()
            cap.release()
            if ret:
                frame_path = video_path + '_frame.jpg'
                cv2.imwrite(frame_path, frame)
                return frame_path
            return None
        except:
            return None


class ContentGeneratorService:
    """Service for generating social media content"""
    
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
        debug_print("Content generator service ready")
    
    def generate_content(self, image_analysis, transcript="", is_video=False):
        """Generate social media content using Gemini"""
        
        # Check if there was an error from vision service
        if image_analysis and image_analysis.get('error'):
            debug_print(f"Vision service error: {image_analysis.get('error')}")
            return {
                'error': image_analysis.get('error'),
                'code': image_analysis.get('code'),
                'retry_after': image_analysis.get('retry_after', 60)
            }
        
        description = image_analysis.get('description', '') if image_analysis else ''
        theme = image_analysis.get('theme', '') if image_analysis else ''
        
        debug_print(f"Generating content for theme: {theme}")
        debug_print(f"Description: {description[:100] if description else 'None'}")
        
        if not description:
            return {
                'error': 'No image description available. Please try again.',
                'code': 'NO_DESCRIPTION'
            }
        
        prompt = f"""Based on this image description: "{description}"

Create social media content for ALL platforms. Theme: {theme}

Return EXACTLY in this format (no extra text, no markdown):

YOUTUBE_TITLE: [short title with emoji, max 70 chars]
YOUTUBE_DESCRIPTION: [2-3 engaging sentences with call to action]
YOUTUBE_TAGS: [5 comma separated tags]

INSTAGRAM_CAPTION: [short caption with emojis and question]
INSTAGRAM_HASHTAGS: [10 space separated hashtags]

FACEBOOK_POST: [short shareable post]
FACEBOOK_HASHTAGS: [5 comma separated hashtags]

LINKEDIN_POST: [professional post, 2 sentences]
LINKEDIN_HASHTAGS: [5 comma separated hashtags]

TWITTER_TWEET: [short tweet under 240 chars]
TWITTER_HASHTAGS: [3 comma separated hashtags]

TIKTOK_CAPTION: [short viral caption]
TIKTOK_HASHTAGS: [5 space separated hashtags]

PINTEREST_TITLE: [short pin title]
PINTEREST_DESCRIPTION: [2 sentence description]
PINTEREST_HASHTAGS: [5 space separated hashtags]"""
        
        response = self._call_gemini_api(prompt)
        
        if response and isinstance(response, dict) and response.get('error'):
            return response
        
        if response:
            debug_print(f"Got response length: {len(response)}")
            parsed = self._parse_response(response)
            return self._ensure_all_sections(parsed, theme, description)
        else:
            return {
                'error': 'Content generation failed. Please try again later.',
                'code': 'GENERATION_FAILED'
            }
    
    def _call_gemini_api(self, prompt):
        """Call Gemini API"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1500,
            }
        }
        
        try:
            debug_print("Calling Gemini for content...")
            response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=60)
            
            if response.status_code == 429:
                debug_print(f"Rate limit (429) hit")
                return {
                    'error': 'Rate limit exceeded. Please wait 1 minute before trying again.',
                    'code': 'RATE_LIMIT',
                    'retry_after': 60
                }
                
            if response.status_code == 403:
                debug_print(f"Authentication error (403)")
                return {
                    'error': 'API key invalid or expired. Please check your Gemini API key.',
                    'code': 'AUTH_ERROR'
                }
                
            if response.status_code == 503:
                debug_print(f"Service unavailable (503)")
                return {
                    'error': 'Gemini API service is temporarily unavailable. Please try again later.',
                    'code': 'SERVICE_UNAVAILABLE'
                }
                
            if response.status_code != 200:
                debug_print(f"API error: {response.status_code}")
                return {
                    'error': f'API error (Status {response.status_code}). Please try again later.',
                    'code': 'API_ERROR'
                }
                
            result = response.json()
            candidates = result.get('candidates', [])
            if candidates:
                parts = candidates[0].get('content', {}).get('parts', [])
                if parts:
                    return parts[0].get('text', '')
            return None
            
        except requests.exceptions.Timeout:
            debug_print(f"Timeout error")
            return {
                'error': 'Request timed out. Please try again.',
                'code': 'TIMEOUT'
            }
        except requests.exceptions.ConnectionError:
            debug_print(f"Connection error")
            return {
                'error': 'Network connection error. Please check your internet.',
                'code': 'CONNECTION_ERROR'
            }
        except Exception as e:
            debug_print(f"API error: {e}")
            return {
                'error': f'Unexpected error: {str(e)}',
                'code': 'UNKNOWN_ERROR'
            }
    
    def _parse_response(self, response):
        """Parse the response"""
        content = {
            'youtube': {'title': '', 'description': '', 'tags': ''},
            'instagram': {'caption': '', 'hashtags': ''},
            'facebook': {'post': '', 'hashtags': ''},
            'linkedin': {'post': '', 'hashtags': ''},
            'twitter': {'tweet': '', 'hashtags': ''},
            'tiktok': {'caption': '', 'hashtags': ''},
            'pinterest': {'title': '', 'description': '', 'hashtags': ''}
        }
        
        lines = response.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            upper_line = line.upper()
            
            if upper_line.startswith('YOUTUBE_TITLE:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'YOUTUBE_TITLE'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('YOUTUBE_DESCRIPTION:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'YOUTUBE_DESCRIPTION'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('YOUTUBE_TAGS:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'YOUTUBE_TAGS'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('INSTAGRAM_CAPTION:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'INSTAGRAM_CAPTION'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('INSTAGRAM_HASHTAGS:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'INSTAGRAM_HASHTAGS'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('FACEBOOK_POST:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'FACEBOOK_POST'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('FACEBOOK_HASHTAGS:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'FACEBOOK_HASHTAGS'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('LINKEDIN_POST:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'LINKEDIN_POST'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('LINKEDIN_HASHTAGS:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'LINKEDIN_HASHTAGS'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('TWITTER_TWEET:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'TWITTER_TWEET'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('TWITTER_HASHTAGS:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'TWITTER_HASHTAGS'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('TIKTOK_CAPTION:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'TIKTOK_CAPTION'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('TIKTOK_HASHTAGS:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'TIKTOK_HASHTAGS'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('PINTEREST_TITLE:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'PINTEREST_TITLE'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('PINTEREST_DESCRIPTION:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'PINTEREST_DESCRIPTION'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif upper_line.startswith('PINTEREST_HASHTAGS:'):
                if current_section:
                    self._save_section(current_section, current_content, content)
                current_section = 'PINTEREST_HASHTAGS'
                current_content = [line.split(':', 1)[1].strip() if ':' in line else '']
            elif current_section:
                current_content.append(line)
        
        if current_section:
            self._save_section(current_section, current_content, content)
        
        return content
    
    def _save_section(self, section, content_list, result):
        """Save parsed section"""
        text = ' '.join(content_list).strip()
        text = re.sub(r'\*\*.*?\*\*', '', text)
        text = text.strip()
        
        mapping = {
            'YOUTUBE_TITLE': ('youtube', 'title'),
            'YOUTUBE_DESCRIPTION': ('youtube', 'description'),
            'YOUTUBE_TAGS': ('youtube', 'tags'),
            'INSTAGRAM_CAPTION': ('instagram', 'caption'),
            'INSTAGRAM_HASHTAGS': ('instagram', 'hashtags'),
            'FACEBOOK_POST': ('facebook', 'post'),
            'FACEBOOK_HASHTAGS': ('facebook', 'hashtags'),
            'LINKEDIN_POST': ('linkedin', 'post'),
            'LINKEDIN_HASHTAGS': ('linkedin', 'hashtags'),
            'TWITTER_TWEET': ('twitter', 'tweet'),
            'TWITTER_HASHTAGS': ('twitter', 'hashtags'),
            'TIKTOK_CAPTION': ('tiktok', 'caption'),
            'TIKTOK_HASHTAGS': ('tiktok', 'hashtags'),
            'PINTEREST_TITLE': ('pinterest', 'title'),
            'PINTEREST_DESCRIPTION': ('pinterest', 'description'),
            'PINTEREST_HASHTAGS': ('pinterest', 'hashtags')
        }
        
        if section in mapping:
            platform, field = mapping[section]
            result[platform][field] = text
            debug_print(f"Saved {section}: {text[:50]}...")
    
    def _ensure_all_sections(self, content, theme, description):
        """Ensure all sections have content"""
        
        # YouTube
        if not content['youtube']['title']:
            content['youtube']['title'] = "Amazing Content! ✨"
        if not content['youtube']['description']:
            content['youtube']['description'] = f"{description}\n\n🔔 Subscribe for more!\n💬 Share your thoughts!"
        if not content['youtube']['tags']:
            content['youtube']['tags'] = "content, viral, trending"
        
        # Instagram
        if not content['instagram']['caption']:
            content['instagram']['caption'] = f"{description}\n\n✨ What do you think? Share below! 👇"
        if not content['instagram']['hashtags']:
            content['instagram']['hashtags'] = "#ContentCreator #Viral #Trending #SocialMedia"
        
        # Facebook
        if not content['facebook']['post']:
            content['facebook']['post'] = f"{description}\n\n📢 Share your thoughts below!"
        if not content['facebook']['hashtags']:
            content['facebook']['hashtags'] = "content, viral, trending"
        
        # LinkedIn
        if not content['linkedin']['post']:
            content['linkedin']['post'] = f"💡 {description}\n\nWhat's your perspective? Share below!"
        if not content['linkedin']['hashtags']:
            content['linkedin']['hashtags'] = "#ContentStrategy, #Professional"
        
        # Twitter
        if not content['twitter']['tweet']:
            content['twitter']['tweet'] = f"{description[:240]}\n\n#Content #Viral"
        if not content['twitter']['hashtags']:
            content['twitter']['hashtags'] = "#Content #Viral"
        
        # TikTok
        if not content['tiktok']['caption']:
            content['tiktok']['caption'] = f"{description[:100]} #viral"
        if not content['tiktok']['hashtags']:
            content['tiktok']['hashtags'] = "#viral #trending #fyp"
        
        # Pinterest
        if not content['pinterest']['title']:
            content['pinterest']['title'] = "Amazing Content"
        if not content['pinterest']['description']:
            content['pinterest']['description'] = description
        if not content['pinterest']['hashtags']:
            content['pinterest']['hashtags'] = "#inspiration #content"
        
        return content