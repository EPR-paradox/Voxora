#!/usr/bin/env bash
# Start the Voxora API with the real providers (DeepSeek + faster-whisper + Piper).
#
# Why a script instead of editing backend/.env: pydantic-settings gives environment variables
# priority over the file, so the DeepSeek key can be read from ~/.hermes/.env at launch and never
# written into the repo, a log, or a shell history. `backend/.env` keeps `AI_PROVIDER=mock` on
# purpose — the test suite assumes it.
#
# Safe to run in the foreground; for a long-running instance use
#   setsid nohup infra/run-api.sh >> /tmp/voxora-api.log 2>&1 &
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"
HERMES_ENV="${HOME}/.hermes/.env"

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "run-api: no interpreter at ${VENV_PYTHON}" >&2
  exit 1
fi

api_key="$(grep -E '^DEEPSEEK_API_KEY=' "${HERMES_ENV}" 2>/dev/null | head -1 | cut -d= -f2-)"
if [ -z "${api_key}" ]; then
  echo "run-api: DEEPSEEK_API_KEY is not set in ${HERMES_ENV}" >&2
  exit 1
fi

# --- roleplay + evaluation (design §8.6) -------------------------------------------------------
export AI_PROVIDER=openai_compatible
export AI_BASE_URL=https://api.deepseek.com/v1
export AI_MODEL=deepseek-flash
export AI_API_KEY="${api_key}"
export AI_MAX_TOKENS=2000
export AI_TIMEOUT_SECONDS=30

# --- transcription: faster-whisper on the CPU (design §8.6, §7.11) -----------------------------
# SPEECH_DEVICE=cpu is deliberate on this box: the CUDA runtime libraries CTranslate2 wants are
# ~1.2 GB and the CPU int8 path already runs at 11.6x realtime.
export SPEECH_PROVIDER=faster_whisper
# Keep the loader off the network. The weights are already in ~/.cache/huggingface, so a revision
# check can only add latency — and on this box, behind a fake-ip resolver and a proxy that comes and
# goes, it can hang outright. Measured: loading small.en is 0.85 s either way, so this is hardening,
# not the fix for a slow start.
export HF_HUB_OFFLINE=1
export SPEECH_MODEL=small.en
export SPEECH_DEVICE=cpu
export SPEECH_COMPUTE_TYPE=int8
export SPEECH_TIMEOUT_SECONDS=180

# --- synthesis: Piper, in-process (docs/meeting-mode-v0.1.md §9) --------------------------------
# Not edge_tts: measured 6.4-10.1 s per line from this network, against 0.2 s for Piper.
export SPEECH_SYNTHESIS_PROVIDER=piper
export SPEECH_SYNTHESIS_PIPER_DIR="${VOXORA_PIPER_DIR:-${HOME}/piper-voices}"
export SPEECH_SYNTHESIS_TIMEOUT_SECONDS=30
# WAV over a phone's uplink is the bottleneck (~320 KB against 0.2 s to synthesise it);
# 48 kbps mono cuts that ~7x for ~18 ms of CPU. 0 keeps the raw WAV.
export SPEECH_SYNTHESIS_MP3_BIT_RATE=48

# --- meeting mode (design §7.14) ----------------------------------------------------------------
# How many times a meeting may continue without the learner speaking.
export MEETING_MAX_ADVANCES=10

# --- public exposure ----------------------------------------------------------------------------
# Bound on 0.0.0.0 so the LAN and the Cloudflare tunnel can reach it. uvicorn's proxy-header
# handling (on by default, trusting X-Forwarded-For only from 127.0.0.1) is what turns a tunnelled
# request into a non-loopback client and makes the Bearer token mandatory — do not widen
# --forwarded-allow-ips.
unset api_key

cd "${REPO_ROOT}/backend"
exec "${VENV_PYTHON}" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
