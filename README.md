# SocialGenius AI — Turn One Upload into Platform-Ready Social Media Posts

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Django](https://img.shields.io/badge/Django-4.2.11-green.svg)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-purple.svg)
![Whisper](https://img.shields.io/badge/Speech-OpenAI%20Whisper-orange.svg)

A Django web application that generates platform-optimized social media content from a single input — an image, a video, or plain text. Upload media, and SocialGenius AI analyzes it with Google Gemini (plus OpenCV for media analysis and OpenAI Whisper for audio transcription) and produces ready-to-post content for YouTube, Instagram, Facebook, LinkedIn, Twitter/X, TikTok, and Pinterest.

## Overview

Creators repurpose the same content across many platforms, each with its own format. SocialGenius AI automates that repurposing: the core engine lives in a large service layer (`content/services.py`) that handles media analysis, transcription, trend signals, and Gemini prompting, while Django views expose both a simple web flow (home → result) and a JSON API with background-job support, analytics endpoints, and A/B-testing endpoints.

## Key Features

- **Image analysis** — upload an image and get a detailed description that seeds all platform content
- **Video processing** — frame extraction/analysis with OpenCV and audio transcription with OpenAI Whisper (cached, with feature flags)
- **Text optimization** — turn plain text into engaging, platform-specific posts
- **Seven platforms, tailored output:**
  - YouTube — SEO title, description, and tags
  - Instagram — caption with hashtag set
  - Facebook — shareable post with hashtags
  - LinkedIn — professional post with industry hashtags
  - Twitter/X — short, punchy tweet with hashtags
  - TikTok — viral-style caption with tags
  - Pinterest — SEO-optimized title and description
- **Smart content detection** — recognizes content categories such as digital marketing, nature, business, food, fitness, travel, technology, and education
- **Trend signals (optional)** — DuckDuckGo-based trend detection and TF-IDF trend matching with scikit-learn, controlled by feature flags
- **API + background jobs** — JSON generation endpoints, submit-job / job-status / job-result endpoints, and optional Celery support
- **Analytics & A/B testing endpoints** — track generated content and compare prompt variants (service layer with graceful fallbacks)
- **Rate-limit aware** — Gemini errors and quota limits surface as user-friendly messages, with a fallback content path when the API is unavailable
- **One-click copy & responsive UI** — copy any platform's output and use the app on any device

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Django 4.2.11, Django REST Framework |
| AI | Google Gemini (`google-generativeai`), OpenAI Whisper (transcription) |
| Media | OpenCV, Pillow, FFmpeg (for video processing), NumPy |
| Async / infra | Celery + Redis (optional), Gunicorn, django-cors-headers |
| Trends | duckduckgo-search, scikit-learn (TF-IDF), BeautifulSoup |
| Database | SQLite by default; psycopg2 included for PostgreSQL |
| Config | python-decouple / python-dotenv |

See `social_media_content_manager/requirements.txt` for the full pinned dependency list.

## Project Structure

```
social-media-content-creator-/
└── social_media_content_manager/       # Django project root
    ├── manage.py
    ├── requirements.txt
    ├── social_media_content_manager/   # Project settings, URLs, WSGI/ASGI
    ├── content/                        # Main application
    │   ├── services.py                 # Core engine: Gemini, Whisper,
    │   │                               # OpenCV, trends, caching, jobs
    │   ├── analytics.py                # Analytics service
    │   ├── ab_testing.py               # A/B testing service
    │   ├── views.py                    # Web + API views
    │   └── urls.py
    └── templates/content/              # home.html, result.html
```

## Getting Started

### Prerequisites

- Python 3.10+
- FFmpeg (for video processing)
- A Google Gemini API key

### Installation

```bash
git clone https://github.com/datascientist970/social-media-content-creator-.git
cd social-media-content-creator-/social_media_content_manager

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ in your browser.

### Configuration

Set your Gemini API key in the project settings / `.env` (loaded via python-decouple). Optional features — OpenCV analysis, DuckDuckGo trends, YouTube API, audio transcription, and the Gemini fallback — are toggled through feature-flag settings documented in `content/services.py`. Never commit a real API key to version control.

## Usage

1. Open the home page and upload an image or video, or paste text.
2. Submit — the app analyzes the media (and transcribes audio, for video) and generates content for all seven platforms.
3. On the result page, review each platform's post and copy it with one click.
4. Developers can also call the API endpoints for generation, background jobs, analytics, and A/B tests (see `content/urls.py`).

## Author

**Muhammad Dawood** — AI & Data Science Engineer
- GitHub: https://github.com/datascientist970
- Location: Mardan, Pakistan

## License

This project is shared for learning and portfolio purposes. Add a license file before reusing it commercially.
