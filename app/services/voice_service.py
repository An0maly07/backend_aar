"""Voice Trigger -> Verify Command.

Speech-to-text runs on the device (e.g. the browser's Web Speech API). The
backend checks the transcript against the user's trigger phrases with a
tolerant fuzzy match, because recognisers often garble words under stress.
"""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class VoiceMatch:
    matched: bool
    phrase: str | None
    score: float


def normalize(text: str) -> str:
    return _SPACES.sub(" ", _NON_WORD.sub(" ", text.casefold())).strip()


def match_transcript(transcript: str, phrases: list[str], threshold: float) -> VoiceMatch:
    words = normalize(transcript).split()
    best_phrase, best_score = None, 0.0
    for phrase in phrases:
        target = normalize(phrase)
        size = len(target.split())
        if not target or not words:
            continue
        # Compare against every window of the same word count ("please help me now" -> "help me").
        for start in range(max(1, len(words) - size + 1)):
            window = " ".join(words[start:start + size])
            score = 1.0 if window == target else SequenceMatcher(None, window, target).ratio()
            if score > best_score:
                best_phrase, best_score = phrase, score
    matched = best_score >= threshold
    return VoiceMatch(matched, best_phrase if matched else None, round(best_score, 3))
