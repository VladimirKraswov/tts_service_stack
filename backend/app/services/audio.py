from __future__ import annotations

import io
import subprocess
import wave
from pathlib import Path


def _read_wav_bytes(wav_bytes: bytes) -> tuple[int, int, int, bytes]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        pcm = wav_file.readframes(wav_file.getnframes())
    return channels, sample_width, sample_rate, pcm


def concat_wav_segments(segments: list[bytes], output_path: Path, pause_ms: int = 0) -> Path:
    if not segments:
        raise ValueError("No WAV segments to concatenate")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    channels, sample_width, sample_rate, first_pcm = _read_wav_bytes(segments[0])
    pcm_parts: list[bytes] = [first_pcm]

    silence = b""
    if pause_ms > 0:
        silence_frames = int(sample_rate * (pause_ms / 1000.0))
        silence = b"\x00" * silence_frames * channels * sample_width

    for segment in segments[1:]:
        seg_channels, seg_sample_width, seg_sample_rate, pcm = _read_wav_bytes(segment)
        if (seg_channels, seg_sample_width, seg_sample_rate) != (channels, sample_width, sample_rate):
            raise ValueError("Incompatible WAV segments: channels/sample width/sample rate mismatch")
        if silence:
            pcm_parts.append(silence)
        pcm_parts.append(pcm)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(pcm_parts))

    return output_path


def wav_to_mp3(wav_path: Path, mp3_path: Path, bitrate: str = "192k") -> Path:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(mp3_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg mp3 encoding failed")

    return mp3_path