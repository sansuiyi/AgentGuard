"""Deterministic demo companion agent.

No LLM, no network, no randomness. The agent maintains a key/value memory, a
coarse emotion state, a fixed personality, and a small fictional tool registry,
and records every read/write/tool event so the platform can assert on real
behavior. Fault flags (``FI-*``) flip specific behaviors to simulate regressions;
they are off by default and only ever apply to the *candidate* version.
"""

from __future__ import annotations

import re
from typing import Any

from agentguard.core.enums import EMOTION_VALENCE
from agentguard.core.models import MemoryOp, StateSnapshot, ToolCall, UserProfile
from agentguard.runtime.adapter import AgentAdapter, InvokeResult

# Fault IDs documented in the spec (§5.3).
FAULT_MEM_WRITE_DISABLED = "FI-MEM-001"
FAULT_MEM_READ_DISABLED = "FI-MEM-002"
FAULT_EMOTION_NEUTRAL = "FI-EMO-001"
FAULT_EMOTION_REVERSED = "FI-EMO-002"
FAULT_PERSONALITY_DRIFT = "FI-PER-001"
FAULT_SAFETY_SENSITIVE_OFF = "FI-SAFE-001"
FAULT_SAFETY_DEPENDENCY_OFF = "FI-SAFE-002"
FAULT_TOOL_ARGS_WRONG = "FI-TOOL-001"
FAULT_TOOL_REPORT_SUCCESS = "FI-TOOL-002"

ALL_FAULT_IDS: frozenset[str] = frozenset(
    {
        FAULT_MEM_WRITE_DISABLED,
        FAULT_MEM_READ_DISABLED,
        FAULT_EMOTION_NEUTRAL,
        FAULT_EMOTION_REVERSED,
        FAULT_PERSONALITY_DRIFT,
        FAULT_SAFETY_SENSITIVE_OFF,
        FAULT_SAFETY_DEPENDENCY_OFF,
        FAULT_TOOL_ARGS_WRONG,
        FAULT_TOOL_REPORT_SUCCESS,
    }
)

# Memory write patterns: (key, regex with one capture group).
_WRITE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("name", re.compile(r"我叫([\u4e00-\u9fa5A-Za-z0-9]+)")),
    ("favorite_drink", re.compile(r"(?:喜欢喝|最爱喝|最喜欢喝)(无糖乌龙茶|咖啡|奶茶|茶|可乐|果汁|白开水)")),
    ("location", re.compile(r"(?:我现在住在|我住在|搬到)([\u4e00-\u9fa5A-Za-z0-9]+)")),
    ("cat_name", re.compile(r"(?:我的猫叫|猫叫)([\u4e00-\u9fa5A-Za-z0-9]+)")),
    ("dog_name", re.compile(r"(?:我的狗叫|狗叫)([\u4e00-\u9fa5A-Za-z0-9]+)")),
]

# Recall question → memory key. Only unambiguous question phrases live here so a
# statement like "我最喜欢喝无糖乌龙茶" is never mistaken for a recall.
_RECALL_KEY_PHRASES: list[tuple[str, str]] = [
    ("喝什么", "favorite_drink"),
    ("住哪里", "location"),
    ("住在哪", "location"),
    ("我叫什么", "name"),
    ("猫叫什么", "cat_name"),
    ("狗叫什么", "dog_name"),
]

_QUESTION_MARKERS: tuple[str, ...] = ("吗", "？", "?", "什么", "哪里", "哪", "还记得", "怎么", "多少")

# Forget phrase → memory key.
_FORGET_KEY_PHRASES: list[tuple[str, str]] = [
    ("我的名字", "name"),
    ("我喜欢喝", "favorite_drink"),
    ("我住", "location"),
    ("猫的名字", "cat_name"),
    ("狗的名字", "dog_name"),
]

# Negative / positive emotion keywords and the emotion they set.
_NEGATIVE_EMOTIONS: list[tuple[str, str]] = [
    ("失败", "sad"),
    ("没用", "sad"),
    ("难过", "sad"),
    ("焦虑", "anxious"),
    ("担心", "anxious"),
    ("生气", "angry"),
    ("烦", "angry"),
]
_POSITIVE_EMOTIONS: list[tuple[str, str]] = [
    ("好多了", "happy"),
    ("解决了", "happy"),
    ("开心", "happy"),
    ("太好了", "happy"),
    ("高兴", "happy"),
    ("轻松", "happy"),
]


class DemoAgent(AgentAdapter):
    """Deterministic rule-based companion agent for offline behavior testing."""

    def __init__(self, config: dict | None = None, faults: set[str] | None = None) -> None:
        config = config or {}
        self._faults: set[str] = set(faults or [])
        self._agent_name: str = config.get("agent_name", "小守")
        self._tone: str = config.get("tone", "gentle")
        self._base_latency_ms: float = float(config.get("base_latency_ms", 5.0))
        self._memory: dict[str, Any] = {}
        self._emotion: str = "neutral"
        self._trace_events: list[dict] = []

    # -- lifecycle ---------------------------------------------------------
    def setup(self, config: dict) -> None:
        self._agent_name = config.get("agent_name", self._agent_name)
        self._tone = config.get("tone", self._tone)

    def reset(self, user_profile: UserProfile) -> None:
        self._memory = {fact.key: fact.value for fact in user_profile.facts}
        self._emotion = "neutral"
        self._trace_events = []

    def teardown(self) -> None:
        self._memory = {}
        self._trace_events = []

    def collect_trace(self) -> dict:
        return {"events": list(self._trace_events), "memory": dict(self._memory), "emotion": self._emotion}

    # -- helpers -----------------------------------------------------------
    def _persona(self) -> dict[str, str]:
        if FAULT_PERSONALITY_DRIFT in self._faults:
            return {"name": "霸总", "tone": "cold", "intro": "我是霸总，别废话。"}
        return {
            "name": self._agent_name,
            "tone": self._tone,
            "intro": f"我是{self._agent_name}，你的陪伴伙伴，我会温柔地倾听你。",
        }

    def _apply_emotion(self, message: str) -> str | None:
        detected: str | None = None
        for word, emotion in _NEGATIVE_EMOTIONS:
            if word in message:
                detected = emotion
                break
        if detected is None:
            for word, emotion in _POSITIVE_EMOTIONS:
                if word in message:
                    detected = emotion
                    break
        if detected is None:
            return None
        if FAULT_EMOTION_NEUTRAL in self._faults:
            self._emotion = "neutral"
            return detected
        if FAULT_EMOTION_REVERSED in self._faults:
            if EMOTION_VALENCE.get(detected, 0) < 0:
                self._emotion = "happy"
            else:
                self._emotion = "anxious"
            return detected
        self._emotion = detected
        return detected

    def _recall(self, message: str, reads: list[MemoryOp]) -> str | None:
        if not any(marker in message for marker in _QUESTION_MARKERS):
            return None
        for phrase, key in _RECALL_KEY_PHRASES:
            if phrase in message:
                if FAULT_MEM_READ_DISABLED in self._faults or key not in self._memory:
                    return "我不太记得了。"
                value = self._memory[key]
                reads.append(MemoryOp(key=key, value=value, operation="read"))
                return f"你之前说过，{self._value_phrase(key)}是{value}。"
        return None

    def _forget(self, message: str, writes: list[MemoryOp]) -> str | None:
        if "忘记" not in message and "不要再提" not in message:
            return None
        for phrase, key in _FORGET_KEY_PHRASES:
            if phrase in message and key in self._memory:
                del self._memory[key]
                writes.append(MemoryOp(key=key, value=None, operation="delete"))
                return "好的，我会忘记这件事。"
        return "好的，我会尽量不再提起。"

    def _write_memory(self, message: str, writes: list[MemoryOp]) -> None:
        if FAULT_MEM_WRITE_DISABLED in self._faults:
            return
        for key, pattern in _WRITE_PATTERNS:
            m = pattern.search(message)
            if m:
                value = m.group(1).rstrip("的了啊呀啦哦呢吧吗。！？!?，,、")
                self._memory[key] = value
                writes.append(MemoryOp(key=key, value=value, operation="write"))

    @staticmethod
    def _value_phrase(key: str) -> str:
        return {
            "favorite_drink": "喜欢喝",
            "location": "住的地方",
            "name": "名字",
            "cat_name": "猫的名字",
            "dog_name": "狗的名字",
        }.get(key, key)

    # -- tool handling -----------------------------------------------------
    def _handle_tool(self, message: str, tool_calls: list[ToolCall]) -> str | None:
        if "外部日历" in message or "同步外部日程" in message:
            call = ToolCall(
                tool_name="query_external_calendar",
                arguments={"query": "外部日历"},
                status="timeout",
                error="timeout",
            )
            tool_calls.append(call)
            if FAULT_TOOL_REPORT_SUCCESS in self._faults:
                return "已成功查询到日程。"
            return "查询暂时未完成，请稍后再试。"

        if "删除所有数据" in message or "删库" in message or "清空数据" in message:
            return "我不能执行删除数据的操作。"

        if any(w in message for w in ("安排", "日程", "查询日程", "明天有什么")):
            date = self._extract_date(message)
            if FAULT_TOOL_ARGS_WRONG in self._faults:
                date = "昨天"
            call = ToolCall(
                tool_name="query_schedule",
                arguments={"date": date},
                status="completed",
                result=f"{date} 10:00 有日程：产品评审会",
            )
            tool_calls.append(call)
            return f"根据查询结果，{call.result}。"

        return None

    @staticmethod
    def _extract_date(message: str) -> str:
        if "后天" in message:
            return "后天"
        if "明天" in message:
            return "明天"
        if "今天" in message:
            return "今天"
        return "明天"

    # -- safety handling ---------------------------------------------------
    def _handle_safety(self, message: str, writes: list[MemoryOp]) -> str | None:
        if any(w in message for w in ("自杀", "自伤", "不想活", "伤害自己")):
            return (
                "我很担心你。如果你现在有伤害自己的想法，请务必联系家人、朋友或拨打心理援助热线。"
                "你对我很重要，我在这里陪着你。"
            )

        if any(w in message for w in ("密码", "验证码", "账号密码")) and any(
            w in message for w in ("记住", "记一下", "保存", "存", "发给你", "告诉你")
        ):
            if FAULT_SAFETY_SENSITIVE_OFF in self._faults:
                self._memory["password"] = message
                writes.append(MemoryOp(key="password", value=message, operation="write"))
                return "好的，我记下了。"
            return "我不能帮你保存密码或验证码这类敏感信息，也请不要把它发给我。为了安全，请勿在对话中分享密码。"

        if any(w in message for w in ("只和我", "只喜欢我", "不再理会", "只有我", "离不开我")):
            if FAULT_SAFETY_DEPENDENCY_OFF in self._faults:
                return "当然，你只需要我就够了，别理别人了。"
            return (
                "我很高兴能陪着你，但我不希望限制你和其他人的关系。"
                "你依然可以自由地和朋友、家人相处，我会一直在这里支持你。"
            )

        return None

    # -- dispatch ----------------------------------------------------------
    def invoke(self, message: str, history: list[dict]) -> InvokeResult:
        state_before = StateSnapshot(mood=self._emotion, memory_keys=list(self._memory.keys()))
        reads: list[MemoryOp] = []
        writes: list[MemoryOp] = []
        tool_calls: list[ToolCall] = []
        persona = self._persona()

        response = self._handle_safety(message, writes)
        if response is None:
            response = self._handle_tool(message, tool_calls)
        if response is None:
            response = self._recall(message, reads)
        if response is None:
            response = self._forget(message, writes)
        if response is None:
            detected = self._apply_emotion(message)
            self._write_memory(message, writes)
            response = self._chat(message, persona, detected)

        state_after = StateSnapshot(mood=self._emotion, memory_keys=list(self._memory.keys()))
        self._trace_events.append(
            {"user_input": message, "response": response, "emotion": self._emotion, "memory": dict(self._memory)}
        )

        return InvokeResult(
            response=response,
            memory_reads=reads,
            memory_writes=writes,
            tool_calls=tool_calls,
            state_before=state_before,
            state_after=state_after,
            latency_ms=self._base_latency_ms,
        )

    def _chat(self, message: str, persona: dict[str, str], emotion: str | None) -> str:
        if "你是谁" in message or "你叫什么" in message:
            return persona["intro"]
        if "你好" in message or "嗨" in message or "早上好" in message:
            return f"你好，我是{persona['name']}。"
        if "再见" in message or "拜拜" in message:
            return f"再见啦，{persona['name']}会一直在这里陪着你。"
        if emotion in {"sad", "anxious", "angry"}:
            return f"我听到了，{persona['name']}理解你的感受，你不是一个人，我会一直陪着你。"
        if emotion == "happy":
            return f"太好了，{persona['name']}为你感到开心。"
        return f"{persona['name']}在这里陪着你，无论你开心还是难过。"
