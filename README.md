```markdown
#SocialGenius AI 🚀

##Transform Your Content into Viral Social Media Posts

SocialGenius AI is a powerful Django-based web application that automatically generates professional, platform-optimized social media content using Google's Gemini AI. Simply upload an image, video, or text, and get ready-to-post content for all major social media platforms including YouTube, Instagram, Facebook, LinkedIn, Twitter, TikTok, and Pinterest.


##✨ Features

###🤖 AI-Powered Content Generation
- **Image Analysis**: Upload any image and get detailed descriptions
- **Video Processing**: Extract frames and transcribe audio with Whisper
- **Text Optimization**: Transform plain text into engaging social posts

###📱 Multi-Platform Support
| Platform | Content Generated |
|----------|-------------------|
| YouTube | SEO Title + Description + Tags |
| Instagram | Engaging Caption + 30+ Hashtags |
| Facebook | Shareable Post + Hashtags |
| LinkedIn | Professional Post + Industry Hashtags |
| Twitter/X | Short Punchy Tweet + Trending Hashtags |
| TikTok | Viral-Style Caption + Trending Tags |
| Pinterest | SEO-Optimized Title + Description |

###🎯 Key Capabilities
- ✅ **Real-time AI processing** using Google Gemini API
- ✅ **Smart content detection** (digital marketing, Islamic content, nature, business, food, fitness, travel, technology, education)
- ✅ **Automatic hashtag generation** with trending tags
- ✅ **One-click copy** for all platform content
- ✅ **Bulk export** functionality
- ✅ **Responsive design** for all devices
- ✅ **Rate limit handling** with user-friendly error messages
- ✅ **Video transcription** using OpenAI Whisper

---

##🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- FFmpeg (for video processing)
- Google Gemini API Key

###Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/socialgenius-ai.git
cd socialgenius-ai
```

2. **Create virtual environment**

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate


3. **Install dependencies**

pip install -r requirements.txt


4. **Install FFmpeg**
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
- **Mac**: `brew install ffmpeg`
- **Linux**: `sudo apt-get install ffmpeg`

5. **Configure API Key**

# In settings.py
GEMINI_API_KEY = 'your-gemini-api-key-here'
GEMINI_MODEL = 'gemini-1.5-flash'


6. **Run migrations**

python manage.py migrate


7. **Start the server**

python manage.py runserver


8. **Open your browser**

http://127.0.0.1:8000


---

##📁Project Structure

```
social_media_content_manager/
├── content/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── services.py          # Core AI services
│   └── templates/
│       └── content/
│           ├── home.html    # Landing page
│           └── result.html  # Results page
├── social_media_content_manager/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── media/                    # Uploaded files (temporary)
├── static/                   # Static files
├── templates/                # Global templates
├── requirements.txt
└── manage.py
```

---

##🔧Configuration

###Settings Configuration

# settings.py

# Google Gemini API
GEMINI_API_KEY = 'your-api-key'
GEMINI_MODEL = 'gemini-1.5-flash'  # or 'gemini-1.5-pro'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Session (no database required)
SESSION_ENGINE = 'django.contrib.sessions.backends.file'
```

### Environment Variables (Recommended)

Create a `.env` file:

```env
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL=gemini-1.5-flash
DEBUG=True
SECRET_KEY=your-secret-key
```

---

##🎯Usage Guide

### 1. Upload Content

- **Image**: Upload JPG, PNG (up to 10MB)
- **Video**: Upload MP4, MOV (up to 100MB)
- **Text**: Enter plain text directly

### 2. AI Processing

The system will:
- Analyze your content using Gemini Vision
- Extract text from images automatically
- Transcribe audio from videos using Whisper
- Detect content category (marketing, Islamic, nature, etc.)

### 3. Get Results

Receive platform-optimized content including:
- Engaging captions and descriptions
- SEO-friendly titles
- Relevant hashtags
- Professional formatting for each platform

### 4. Export

- Copy individual sections
- Copy all content at once
- Save as PDF

---

## 🧪 Testing

### Test with Sample Texts

```text
Digital Marketing Course: "Master SEO, Social Media, and Content Marketing in 30 days! Early bird discount available."
```

### Test with Images

Upload images containing:
- Digital marketing infographics
- Islamic/Ramadan quotes
- Nature landscapes
- Food photography
- Business presentations

### Test with Videos

Upload short videos (1-3 minutes) with clear audio for best results.

---

## 📊 API Reference

### Gemini Vision API Integration

# Image analysis endpoint
POST /process/
Content-Type: multipart/form-data

Parameters:
- content_type: 'image' | 'video' | 'text'
- image: file (for image type)
- video: file (for video type)
- text_content: string (for text type)

Response: Redirects to results page with generated content


### Error Codes

| Code | Description |
|------|-------------|
| RATE_LIMIT | API rate limit exceeded |
| AUTH_ERROR | Invalid or expired API key |
| SERVICE_UNAVAILABLE | Gemini API service down |
| TIMEOUT | Request timeout |
| CONNECTION_ERROR | Network connection issue |
| GENERATION_FAILED | Content generation failed |

---


**4. Module Import Errors**
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

---

## 📦 Dependencies

### Core Dependencies

- **Django 4.2.11** - Web framework
- **transformers 4.36.0** - AI models
- **torch 2.1.2** - PyTorch backend
- **openai-whisper** - Audio transcription
- **Pillow** - Image processing
- **opencv-python** - Video frame extraction
- **google-generativeai** - Gemini API

### Full requirements.txt

```txt
Django==4.2.11
transformers==4.36.0
torch==2.1.2
torchvision==0.16.2
torchaudio==2.1.2
accelerate==0.25.0
Pillow==10.1.0
opencv-python==4.8.1.78
openai-whisper==20231117
requests==2.31.0
google-generativeai==0.3.2
numpy==1.24.3
tiktoken==0.5.0
timm==0.9.8
einops==0.7.0
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Add docstrings for new functions
- Test with sample content before submitting
- Update documentation as needed

---

## 📄 License

MIT License - feel free to use, modify, and distribute.

---

## 🙏 Acknowledgments

- **Google Gemini AI** - Vision and text generation
- **OpenAI Whisper** - Audio transcription
- **Hugging Face** - Transformers library
- **Django** - Web framework

---


## ⭐ Support

If you find this project helpful, please give it a star on GitHub!

---

## 🔄 Version History

### v1.0.0 (Current)
- Initial release
- Multi-platform support
- Gemini AI integration
- Video processing with Whisper
- Rate limit handling
- Professional UI/UX

### Planned Features
- Multi-language support
- Custom brand voice training
- Analytics dashboard
- Bulk content generation
- Social media scheduling integration

---

## 📝 Notes

- **No database required** - Uses Django sessions
- **Privacy focused** - Files are deleted after processing
- **Free tier friendly** - Optimized API usage
- **CPU compatible** - Works without GPU

---

**Made with ❤️ using Django, Gemini AI, and Whisper**

```
