import os
import uuid
import json
import hashlib
import concurrent.futures
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
from .services import (
    GeminiVisionService, WhisperService, GoogleSTTService,
    VideoFrameExtractor, SceneDetector, AudioProcessor,
    TranscriptMerger, TranscriptCorrectionService, ContentGeneratorService
)

vision_service = None
whisper_service = None
google_stt_service = None
frame_extractor = None
correction_service = None
generator_service = None
_result_cache = {}

def get_services():
    global vision_service, whisper_service, google_stt_service, frame_extractor, correction_service, generator_service
    if vision_service is None:
        vision_service = GeminiVisionService()
    if whisper_service is None:
        whisper_service = WhisperService()
    if google_stt_service is None:
        google_stt_service = GoogleSTTService()
    if frame_extractor is None:
        frame_extractor = VideoFrameExtractor()
    if correction_service is None:
        correction_service = TranscriptCorrectionService()
    if generator_service is None:
        generator_service = ContentGeneratorService()
    return vision_service, whisper_service, google_stt_service, frame_extractor, correction_service, generator_service

def get_cache_key(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read(1024 * 1024)).hexdigest()
    return None

def api_status(request):
    return JsonResponse({'status': 'online', 'message': 'API ready'})

def home(request):
    return render(request, 'content/home.html')

def process(request):
    if request.method != 'POST':
        return redirect('home')
    
    content_type = request.POST.get('content_type')
    print(f"[INFO] Processing: {content_type}")
    
    try:
        vision_service, whisper_service, google_stt_service, frame_extractor, correction_service, generator_service = get_services()
        
        description = ""
        whisper_transcript = ""
        whisper_confidence = 0
        whisper_segments = []
        google_transcript = ""
        google_confidence = 0
        corrected_data = None
        temp_file_path = None
        audio_path = None
        visual_context = None
        frame_paths = []
        merged_transcript = ""
        conflicts = []
        scene_times = []
        
        # ==================== IMAGE PROCESSING ====================
        if content_type == 'image' and request.FILES.get('image'):
            uploaded = request.FILES['image']
            temp_file_path = os.path.join(settings.MEDIA_ROOT, f'temp_{uuid.uuid4().hex}_{uploaded.name}')
            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
            with open(temp_file_path, 'wb+') as f:
                for chunk in uploaded.chunks():
                    f.write(chunk)
            print(f"[INFO] Analyzing image...")
            analysis = vision_service.analyze_image_with_gemini(temp_file_path)
            description = analysis if analysis else f"Image: {uploaded.name}"
            social_content = generator_service.generate_content(
                {'description': description}, content_type="image", user_text=description
            )
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            request.session['result'] = {
                'description': description, 'whisper_transcript': '', 'whisper_confidence': 0,
                'google_transcript': '', 'google_confidence': 0, 'merged_transcript': '',
                'conflicts_count': 0, 'conflicts': [], 'scenes_detected': 0,
                'visual_context': '', 'visual_confidence': 0, 'corrected_transcript': description,
                'main_topic': 'Image Content', 'key_points': [], 'products_services': '',
                'corrections_made': [], 'confidence_score': 0, 'uncertain_sections': [],
                'social': social_content
            }
            return redirect('result')
        
        # ==================== VIDEO PROCESSING ====================
        elif content_type == 'video' and request.FILES.get('video'):
            uploaded = request.FILES['video']
            temp_file_path = os.path.join(settings.MEDIA_ROOT, f'temp_{uuid.uuid4().hex}_{uploaded.name}')
            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
            with open(temp_file_path, 'wb+') as f:
                for chunk in uploaded.chunks():
                    f.write(chunk)
            print(f"[INFO] Processing video: {uploaded.name}")
            
            cache_key = get_cache_key(temp_file_path)
            
            # Extract audio first
            print(f"[INFO] Extracting audio...")
            audio_path = whisper_service.extract_audio(temp_file_path)
            
            if audio_path:
                print(f"[INFO] Cleaning audio...")
                cleaned_audio = AudioProcessor.clean_audio(audio_path)
                audio_for_transcription = cleaned_audio
            else:
                audio_for_transcription = None
            
            # Run transcriptions
            whisper_transcript = ""
            google_transcript = ""
            
            if audio_for_transcription:
                print(f"[INFO] Transcribing with Whisper...")
                whisper_transcript, whisper_confidence, whisper_segments = whisper_service.transcribe_with_timestamps(
                    audio_for_transcription, False
                )
                print(f"[INFO] Whisper confidence: {whisper_confidence:.1f}%")
                
                print(f"[INFO] Transcribing with Google STT...")
                google_transcript, google_confidence = google_stt_service.transcribe_with_confidence(
                    audio_for_transcription
                )
                print(f"[INFO] Google STT confidence: {google_confidence:.1f}%")
            
            # Merge transcripts
            if whisper_transcript or google_transcript:
                merged_transcript, conflicts = TranscriptMerger.merge_transcripts(whisper_transcript, google_transcript)
                print(f"[INFO] Merged transcript length: {len(merged_transcript)}")
                
                # Use the merged transcript as the source
                description = merged_transcript if merged_transcript else whisper_transcript if whisper_transcript else google_transcript
                print(f"[INFO] Description length: {len(description)}")
            else:
                description = f"Video content about a product for kids"
                print(f"[INFO] Using fallback description")
            
            # Clean up audio files
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            if audio_for_transcription and audio_for_transcription != audio_path and os.path.exists(audio_for_transcription):
                os.remove(audio_for_transcription)
            
            # Generate social content - pass the transcript directly
            print(f"[INFO] Generating social content from transcript...")
            social_content = generator_service.generate_content(
                {'corrected_transcript': description}, 
                content_type="video"
            )
            
            # Clean up temp file
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            
            request.session['result'] = {
                'description': description,
                'whisper_transcript': whisper_transcript[:2000] if whisper_transcript else '',
                'whisper_confidence': round(whisper_confidence, 1),
                'google_transcript': google_transcript[:2000] if google_transcript else '',
                'google_confidence': round(google_confidence, 1),
                'merged_transcript': merged_transcript[:2000] if merged_transcript else '',
                'conflicts_count': len(conflicts),
                'conflicts': conflicts[:5] if conflicts else [],
                'scenes_detected': len(scene_times),
                'visual_context': '',
                'visual_confidence': 0,
                'corrected_transcript': description,
                'main_topic': 'Product Review',
                'key_points': [],
                'products_services': 'ATM Money Box',
                'corrections_made': [],
                'confidence_score': (whisper_confidence + google_confidence) / 2 if (whisper_confidence or google_confidence) else 0,
                'uncertain_sections': [],
                'social': social_content
            }
            return redirect('result')
        
        # ==================== TEXT PROCESSING ====================
        elif content_type == 'text':
            description = request.POST.get('text_content', '')
            if not description:
                messages.error(request, 'Please enter text content')
                return redirect('home')
            print(f"[INFO] Processing text content...")
            social_content = generator_service.generate_content(
                {}, content_type="text", user_text=description
            )
            request.session['result'] = {
                'description': description, 'whisper_transcript': '', 'whisper_confidence': 0,
                'google_transcript': '', 'google_confidence': 0, 'merged_transcript': '',
                'conflicts_count': 0, 'conflicts': [], 'scenes_detected': 0,
                'visual_context': '', 'visual_confidence': 0, 'corrected_transcript': description,
                'main_topic': 'Text Content', 'key_points': [], 'products_services': '',
                'corrections_made': [], 'confidence_score': 0, 'uncertain_sections': [],
                'social': social_content
            }
            return redirect('result')
        
        else:
            messages.error(request, 'Please select a file or enter text')
            return redirect('home')
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        messages.error(request, f'Error: {str(e)}')
        return redirect('home')

def result(request):
    result_data = request.session.get('result')
    if not result_data:
        messages.error(request, 'No results found')
        return redirect('home')
    return render(request, 'content/result.html', {
        'description': result_data.get('description', ''),
        'whisper_transcript': result_data.get('whisper_transcript', ''),
        'whisper_confidence': result_data.get('whisper_confidence', 0),
        'google_transcript': result_data.get('google_transcript', ''),
        'google_confidence': result_data.get('google_confidence', 0),
        'merged_transcript': result_data.get('merged_transcript', ''),
        'conflicts_count': result_data.get('conflicts_count', 0),
        'conflicts': result_data.get('conflicts', []),
        'scenes_detected': result_data.get('scenes_detected', 0),
        'visual_context': result_data.get('visual_context', ''),
        'visual_confidence': result_data.get('visual_confidence', 0),
        'corrected_transcript': result_data.get('corrected_transcript', ''),
        'main_topic': result_data.get('main_topic', ''),
        'key_points': result_data.get('key_points', []),
        'products_services': result_data.get('products_services', ''),
        'corrections_made': result_data.get('corrections_made', []),
        'confidence_score': result_data.get('confidence_score', 0),
        'uncertain_sections': result_data.get('uncertain_sections', []),
        'social': result_data.get('social', {})
    })