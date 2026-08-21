# YouTube Clip Agent

Agente MVP que toma una URL de YouTube, transcribe el video, identifica los momentos más relevantes con un LLM y exporta clips verticales **9:16** listos para social (MP4 + SRT + copy).

## Requisitos

- Python 3.9+
- Node.js 20+ (servidor de PO Tokens para YouTube)
- API key de Google Gemini ([Google AI Studio](https://aistudio.google.com/apikey))
- Chrome (recomendado) con sesión de YouTube iniciada — cookies para evitar 403
- ffmpeg: el proyecto usa `imageio-ffmpeg` (binario embebido)

## Setup

```bash
cd AI-Hackaton-Data-Team-9
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editá .env y seteá GEMINI_API_KEY

chmod +x scripts/setup_ytdlp.sh
./scripts/setup_ytdlp.sh
```

## Arranque

En una terminal (PO Token server — o dejá que la app lo auto-inicie):

```bash
node vendor/bgutil-ytdlp-pot-provider/server/build/main.js --port 4416
```

App:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Abrí [http://localhost:8000](http://localhost:8000), pegá una URL de YouTube y generá clips.

## API

| Método | Path | Descripción |
|--------|------|-------------|
| `POST` | `/jobs` | Crea un job `{ "url", "max_clips", "clip_duration_sec" }` |
| `GET` | `/jobs/{id}` | Estado + clips |
| `GET` | `/jobs/{id}/clips/{clip_id}` | Descarga MP4 |
| `GET` | `/jobs/{id}/clips/{clip_id}/srt` | Descarga SRT |

## Pipeline

1. **yt-dlp** (binario `./bin/yt-dlp`) + PO Tokens + cookies de Chrome  
2. **faster-whisper** — transcripción con timestamps  
3. **Gemini** — scoring de highlights + títulos/captions/hashtags  
4. **ffmpeg** — corte, crop 9:16 (1080×1920) y burn-in opcional de subtítulos  

Artefactos por job en `output/{job_id}/`.

## Config (`.env`)

| Variable | Default | Uso |
|----------|---------|-----|
| `GEMINI_API_KEY` | — | Obligatoria ([AI Studio](https://aistudio.google.com/apikey)) |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Free tier friendly; Pro needs billing |
| `WHISPER_MODEL` | `base` | `tiny` / `base` / `small` / … |
| `WHISPER_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| `OUTPUT_DIR` | `./output` | Carpeta de artefactos |
| `BURN_IN_SUBTITLES` | `false` | Subtítulos quemados en el MP4 |
| `YTDLP_COOKIES_FROM_BROWSER` | vacío | Alternativa: `chrome` / `safari` |
| `YTDLP_COOKIES_FILE` | `./cookies.txt` | Cookies exportadas (recomendado) |
| `POT_BASE_URL` | `http://127.0.0.1:4416` | Servidor bgutil PO Token |

## Troubleshooting

### `HTTP Error 403: Forbidden` al descargar

1. Refrescá cookies (Chrome logueado en YouTube):

```bash
./bin/yt-dlp --cookies-from-browser chrome --cookies cookies.txt \
  --skip-download 'https://www.youtube.com/watch?v=jNQXAC9IVRw'
```

2. Confirmá POT server: `curl http://127.0.0.1:4416/ping`
3. O **subí un MP4 local** desde la UI (evita YouTube por completo)

Más detalle: [PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)

## Fuera de alcance (MVP)

- Auto-post a TikTok / IG / Shorts  
- Monitoreo de channel ID  
- Face-tracking crop
