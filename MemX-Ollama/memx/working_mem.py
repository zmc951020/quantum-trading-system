from typing import List, Dict, Optional
import logging
import time
import json
from .utils import validate_config, desensitize, clamp_priority

logger = logging.getLogger(__name__)

class WorkingMemory:
    def __init__(self, max_tokens: int = 8192):
        self.history: List[Dict[str, str]] = []
        self.max_tokens = max_tokens
        self.summary = ""
        self.priority_scores: Dict[int, float] = {}

    def add(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content, "timestamp": time.time()})
        self._calculate_priority(len(self.history) - 1)
        self.auto_compress()

    def _calculate_priority(self, index: int) -> float:
        if index >= len(self.history):
            return 0.0
        msg = self.history[index]
        priority = 0.5
        if "关键" in msg["content"] or "重要" in msg["content"]:
            priority += 0.2
        if any(word in msg["content"] for word in ["用户", "我", "你"]):
            priority += 0.1
        priority = clamp_priority(priority)
        self.priority_scores[index] = priority
        return priority

    def auto_compress(self) -> None:
        total_tokens = self.count_tokens()
        if total_tokens > self.max_tokens * 0.8:
            self.summary = self.make_summary()
            low_priority_indices = sorted(
                [i for i in self.priority_scores if self.priority_scores[i] < 0.3],
                key=lambda i: self.priority_scores[i]
            )
            for idx in low_priority_indices[:-10]:
                self.history[idx] = None
            self.history = [msg for msg in self.history if msg is not None]
            self.priority_scores = {i: self.priority_scores[i] for i in range(len(self.history)) if i in self.priority_scores}

    def make_summary(self) -> str:
        if len(self.history) <= 3:
            return ""
        recent = self.history[-10:]
        summary_text = "\n".join([f"{msg['role']}: {msg['content'][:50]}..." for msg in recent])
        return f"[摘要-{time.strftime('%H:%M')}]: {summary_text}"

    def count_tokens(self) -> int:
        return sum(len(msg["content"]) // 4 for msg in self.history)

    def get_context(self) -> str:
        context = []
        if self.summary:
            context.append(self.summary)
        for msg in self.history[-10:]:
            context.append(f"{msg['role']}: {msg['content']}")
        return "\n".join(context)

    def clear(self) -> None:
        self.history = []
        self.summary = ""
        self.priority_scores = {}