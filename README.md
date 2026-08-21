# Monk.Clip

From long-form video to social-ready clips.

Monk.Clip toma un video de YouTube (o un MP4 local), encuentra los momentos más fuertes y exporta verticales **9:16** listos para TikTok, Reels y Shorts — con título, caption y hashtags.

Hackathon · Data Team 9

## Qué hace

1. **Download** — ingesta YouTube o un MP4 local y extrae el audio  
2. **Transcribe** — Whisper local con timestamps (sin API de audio)  
3. **Score** — Gemini elige hooks, claims y takeaways  
4. **Export** — corte + crop 1080×1920, MP4 + SRT + copy para postear

## Requisitos

- Python 3.9+
- Node.js 20+ (servidor de PO Tokens para YouTube)
- API key de [Google Gemini](https://aistudio.google.com/apikey)
- Chrome con sesión de YouTube (cookies; evita el 403 de yt-dlp)
- ffmpeg viene embebido vía `imageio-ffmpeg`

## Setup

```bash
cd AI-Hackaton-Data-Team-9
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Editá `.env` y seteá `GEMINI_API_KEY`.

```bash
chmod +x scripts/setup_ytdlp.sh
./scripts/setup_ytdlp.sh
```

## Arranque

En una terminal, el servidor de PO Tokens (o dejá que la app lo inicie sola):

```bash
node vendor/bgutil-ytdlp-pot-provider/server/build/main.js --port 4416
```

En otra:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abrí [http://127.0.0.1:8000](http://127.0.0.1:8000), pegá una URL o subí un MP4, y tocá **Generate**.

## Config (`.env`)

| Variable | Default | Uso |
|----------|---------|-----|
| `GEMINI_API_KEY` | — | Obligatoria |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Free tier; Pro requiere billing |
| `WHISPER_MODEL` | `base` | `tiny` / `base` / `small` / … |
| `WHISPER_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| `OUTPUT_DIR` | `./output` | Artefactos por job |
| `BURN_IN_SUBTITLES` | `false` | Subtítulos quemados en el MP4 |
| `YTDLP_COOKIES_FILE` | `./cookies.txt` | Cookies exportadas (recomendado) |
| `YTDLP_COOKIES_FROM_BROWSER` | vacío | Alternativa: `chrome` / `safari` |
| `POT_BASE_URL` | `http://127.0.0.1:4416` | Servidor bgutil PO Token |

No commitees `.env` ni `cookies.txt`.

## API

| Método | Path | Descripción |
|--------|------|-------------|
| `POST` | `/jobs` | Crea un job `{ "url", "max_clips", "clip_duration_sec" }` |
| `POST` | `/jobs/upload` | Misma idea, con MP4 local |
| `GET` | `/jobs/{id}` | Estado + clips |
| `GET` | `/jobs/{id}/clips/{clip_id}` | Descarga MP4 |
| `GET` | `/jobs/{id}/clips/{clip_id}/srt` | Descarga SRT |

Los archivos de cada job quedan en `output/{job_id}/`.

## Fuera de alcance (MVP)

- Auto-post a TikTok / Instagram / Shorts
- Login con Google (el botón Ingresar es un scroll, por ahora)
- Face-tracking crop
- Duración de clip estricta al segundo (hoy el target es aproximado)
