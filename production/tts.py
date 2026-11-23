#!/usr/bin/env python3
"""Generate voice-over files for the sample scripts with the open-source Kokoro TTS model.

Usage:
  python3 tts.py short --voice bm_george --speed 0.95 --out vo/short_george
  python3 tts.py audition --out vo/auditions

Needs kokoro-onnx (pip) and the model files kokoro-v1.0.onnx + voices-v1.0.bin
(https://huggingface.co/fastrtc/kokoro-onnx). Set KOKORO_DIR to their folder.
"""
import argparse
import os
import re

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

from script import SCRIPTS

# Narrator presets matched to the voice playbook
PRESETS = {
    "storyteller_uk_male": dict(voice="bm_george", speed=0.93, lang="en-gb",
                                label="British storyteller (male)", fits="Living Painting · series"),
    "storyteller_female": dict(voice="af_heart", speed=0.95, lang="en-us",
                               label="Warm storyteller (female)", fits="Living Painting · series"),
    "deep_male": dict(voice="am_onyx", speed=0.9, lang="en-us",
                      label="Deep documentary (male)", fits="Story in 60"),
    "intimate_female": dict(voice="bf_emma", speed=0.85, lang="en-gb",
                            label="Intimate close-mic (female)", fits="Gold Line"),
    "pov_young": dict(voice="af_bella", speed=1.12, lang="en-us",
                      label="Young conversational (female)", fits="POV Diary"),
    "sleep_soft": dict(voice="bf_isabella", speed=0.8, lang="en-gb",
                       label="Soft sleep-story (female)", fits="Sleep Story"),
    "hindi_male": dict(voice="hm_omega", speed=0.95, lang="hi",
                       label="Hindi narrator (male)", fits="Hindi dub"),
}

AUDITION_EN = ("Eight years in Petersburg, and not a single friend. "
               "It was a wonderful night, such a night as is only possible when we are young, dear reader.")
AUDITION_HI = "आठ साल पीटर्सबर्ग में, और एक भी दोस्त नहीं। वह एक अद्भुत रात थी, ऐसी रात जो केवल जवानी में ही होती है।"


def clean(text):
    text = text.replace("…", "...").replace("—", ", ")
    return re.sub(r"\s+", " ", text).strip()


def model():
    d = os.environ.get("KOKORO_DIR", ".")
    return Kokoro(os.path.join(d, "kokoro-v1.0.onnx"), os.path.join(d, "voices-v1.0.bin"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["short", "long", "audition"])
    ap.add_argument("--preset", default="storyteller_uk_male")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    k = model()
    if a.what == "audition":
        for name, p in PRESETS.items():
            text = AUDITION_HI if p["lang"] == "hi" else AUDITION_EN
            s, sr = k.create(text, voice=p["voice"], speed=p["speed"], lang=p["lang"])
            sf.write(os.path.join(a.out, f"{name}.wav"), s, sr)
            print(name, f"{len(s) / sr:.1f}s")
        return
    p = PRESETS[a.preset]
    for i, seg in enumerate(SCRIPTS[a.what]):
        text = clean(seg.get("vo", ""))
        if not text:
            continue
        s, sr = k.create(text, voice=p["voice"], speed=p["speed"], lang=p["lang"])
        s = np.asarray(s, dtype=np.float32)
        sf.write(os.path.join(a.out, f"seg_{i:02d}.wav"), s, sr, subtype="PCM_16")
        print(f"seg_{i:02d} {len(s) / sr:.1f}s  {text[:60]}")


if __name__ == "__main__":
    main()
