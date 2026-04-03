import os
import uuid
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from .services import GeminiVisionService, WhisperService, VideoFrameExtractor, ContentGeneratorService

vision_service = None
whisper_service = None
generator_service = None

def get_services():
    global vision_service, whisper_service, generator_service
    if vision_service is None:
        vision_service = GeminiVisionService()
    if whisper_service is None:
        whisper_service = WhisperService()
    if generator_service is None:
        generator_service = ContentGeneratorService()
    return vision_service, whisper_service, generator_service

def home(request):
    return render(request, 'content/home.html')

def process(request):
    if request.method != 'POST':
        return redirect('home')
    
    content_type = request.POST.get('content_type')
    print(f"[INFO] Processing: {content_type}")
    
    try:
        vision_service, whisper_service, generator_service = get_services()
        
        image_analysis = None
        transcript = ""
        temp_file_path = None
        
        if content_type == 'image' and request.FILES.get('image'):
            uploaded = request.FILES['image']
            temp_file_path = os.path.join(settings.MEDIA_ROOT, f'temp_{uuid.uuid4().hex}_{uploaded.name}')
            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
            
            with open(temp_file_path, 'wb+') as f:
                for chunk in uploaded.chunks():
                    f.write(chunk)
            
            print(f"[INFO] Analyzing image with Gemini...")
            image_analysis = vision_service.analyze_image_with_gemini(temp_file_path)
            
            # Check for errors
            if image_analysis and image_analysis.get('error'):
                error_msg = image_analysis.get('error')
                error_code = image_analysis.get('code')
                
                if error_code == 'RATE_LIMIT':
                    messages.error(request, f'⚠️ {error_msg} Please wait a moment and try again.')
                elif error_code == 'AUTH_ERROR':
                    messages.error(request, f'🔑 {error_msg} Please check your API key configuration.')
                elif error_code == 'SERVICE_UNAVAILABLE':
                    messages.error(request, f'🔄 {error_msg} The service is temporarily unavailable.')
                else:
                    messages.error(request, f'❌ {error_msg}')
                
                # Clean up and redirect
                if temp_file_path and os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                return redirect('home')
            
        elif content_type == 'video' and request.FILES.get('video'):
            uploaded = request.FILES['video']
            temp_file_path = os.path.join(settings.MEDIA_ROOT, f'temp_{uuid.uuid4().hex}_{uploaded.name}')
            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
            
            with open(temp_file_path, 'wb+') as f:
                for chunk in uploaded.chunks():
                    f.write(chunk)
            
            print(f"[INFO] Processing video...")
            
            # Extract and analyze frame
            frame_path = VideoFrameExtractor.extract_first_frame(temp_file_path)
            if frame_path:
                print(f"[INFO] Analyzing video frame...")
                image_analysis = vision_service.analyze_image_with_gemini(frame_path)
                if os.path.exists(frame_path):
                    os.remove(frame_path)
            
            # Check for errors
            if image_analysis and image_analysis.get('error'):
                error_msg = image_analysis.get('error')
                error_code = image_analysis.get('code')
                
                if error_code == 'RATE_LIMIT':
                    messages.error(request, f'⚠️ {error_msg} Please wait a moment and try again.')
                elif error_code == 'AUTH_ERROR':
                    messages.error(request, f'🔑 {error_msg} Please check your API key configuration.')
                else:
                    messages.error(request, f'❌ {error_msg}')
                
                if temp_file_path and os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                return redirect('home')
            
            # Transcribe audio
            if image_analysis and not image_analysis.get('error'):
                print(f"[INFO] Transcribing audio...")
                transcript = whisper_service.transcribe(temp_file_path, is_video=True)
            
        elif content_type == 'text':
            text_content = request.POST.get('text_content', '')
            image_analysis = {
                'description': text_content,
                'theme': 'text',
                'is_islamic': False,
                'success': True
            }
        
        else:
            messages.error(request, 'Please select a file or enter text')
            return redirect('home')
        
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        
        # Generate social content
        social_content = generator_service.generate_content(
            image_analysis,
            transcript,
            content_type == 'video'
        )
        
        # Check for content generation errors
        if social_content and social_content.get('error'):
            error_msg = social_content.get('error')
            error_code = social_content.get('code')
            
            if error_code == 'RATE_LIMIT':
                messages.error(request, f'⚠️ {error_msg} Please wait a moment and try again.')
            elif error_code == 'AUTH_ERROR':
                messages.error(request, f'🔑 {error_msg} Please check your API key configuration.')
            else:
                messages.error(request, f'❌ {error_msg}')
            return redirect('home')
        
        # Store in session
        request.session['result'] = {
            'description': image_analysis.get('description', ''),
            'transcript': transcript,
            'social': social_content
        }
        
        return redirect('result')
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f'❌ Error: {str(e)}')
        return redirect('home')

def result(request):
    result_data = request.session.get('result')
    if not result_data:
        messages.error(request, 'No results found')
        return redirect('home')
    
    return render(request, 'content/result.html', {
        'description': result_data['description'],
        'transcript': result_data.get('transcript', ''),
        'social': result_data['social']
    })