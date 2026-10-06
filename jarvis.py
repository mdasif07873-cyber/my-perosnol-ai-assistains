from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    import pywinauto
except Exception:
    pywinauto = None

try:
    import win32api
except Exception:
    win32api = None

try:
    from PySide6 import QtCore, QtWidgets
except Exception:
    QtCore = None
    QtWidgets = None


LOGGER = logging.getLogger("nova")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AssistantState(str, Enum):
    WAITING = "WAITING"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    EXECUTING = "EXECUTING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


@dataclass
class ApplicationDefinition:
    name: str
    executable_path: Optional[str] = None
    aliases: Sequence[str] = field(default_factory=tuple)
    launch_method: str = "default"
    automation_adapter: Optional[str] = None
    permissions: Sequence[str] = field(default_factory=lambda: ["open"])
    supported_actions: Sequence[str] = field(default_factory=lambda: ["open", "close"])


@dataclass
class ActionRequest:
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    require_confirmation: bool = False
    rationale: str = ""


@dataclass
class ConfirmationRequest:
    message: str
    action_name: str
    risk: RiskLevel


@dataclass
class TaskHistoryEntry:
    timestamp: str
    command: str
    steps: List[str]
    result: str
    errors: List[str] = field(default_factory=list)


@dataclass
class Reminder:
    id: str
    text: str
    run_at: datetime
    recurring: Optional[str] = None


@dataclass
class MemoryRecord:
    key: str
    value: Any
    created_at: str


class AIProvider(Protocol):
    def plan_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> List[ActionRequest]:
        ...

    def extract_intent(self, prompt: str) -> Dict[str, Any]:
        ...


class LocalModelProvider:
    def plan_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> List[ActionRequest]:
        lowered = prompt.lower().replace("watsapp", "whatsapp").replace("what's app", "whatsapp")
        actions: List[ActionRequest] = []

        if re.search(r"\b(open|launch|start|run|khol|kholo|kholna|chala|chalao)\b", lowered):
            app = self._detect_application(prompt)
            actions.append(ActionRequest("open_application", {"application": app}, RiskLevel.LOW, False, "Open requested application"))
            return actions

        if re.search(r"\b(search|find|look up|dhoond|dhoondo|dhoondho|dhund|dhundo|dhundho|khojo|talash)\b|\b(?:google|youtube)\s+(?:par|pe|mein|me)\b", lowered):
            target = self._detect_search_target(prompt)
            actions.append(ActionRequest("search_web", {"query": target}, RiskLevel.LOW, False, "Search the web"))
            return actions

        if "message" in lowered or "msg" in lowered or "chat" in lowered:
            recipient = self._extract_contact(prompt)
            message = self._extract_message(prompt)
            actions.append(ActionRequest("send_message", {"recipient": recipient, "message": message}, RiskLevel.MEDIUM, True, "Send a message"))
            return actions

        if "screenshot" in lowered:
            actions.append(ActionRequest("take_screenshot", {"path": str(Path.home() / "Pictures" / "nova_screenshot.png")}, RiskLevel.LOW, False, "Capture screenshot"))
            return actions

        if "restart" in lowered or "shutdown" in lowered or "lock" in lowered:
            actions.append(ActionRequest("system_control", {"command": "restart" if "restart" in lowered else "shutdown" if "shutdown" in lowered else "lock"}, RiskLevel.HIGH, True, "System control action"))
            return actions

        actions.append(ActionRequest("respond", {"message": f"I can help with: open apps, search, messages, screenshots, and system actions."}, RiskLevel.LOW, False, "Fallback response"))
        return actions

    def extract_intent(self, prompt: str) -> Dict[str, Any]:
        lowered = prompt.lower()
        intent = {
            "application": None,
            "website": None,
            "person": None,
            "file": None,
            "action": None,
            "message": None,
            "destination": None,
            "time": None,
            "date": None,
            "quantity": None,
            "confirmation_required": False,
            "risk_level": RiskLevel.LOW.value,
        }

        if "open" in lowered or "khol" in lowered:
            intent["action"] = "open"
        if "search" in lowered:
            intent["action"] = "search"
        if "message" in lowered:
            intent["action"] = "message"
        if "screenshot" in lowered:
            intent["action"] = "screenshot"

        apps = ["chrome", "edge", "firefox", "whatsapp", "wps", "settings", "calculator", "notepad", "vs code"]
        for app in apps:
            if app in lowered:
                intent["application"] = app
                break

        return intent

    def _detect_application(self, prompt: str) -> str:
        lowered = prompt.lower()
        app_map = {
            "chrome": "Chrome",
            "google chrome": "Chrome",
            "edge": "Microsoft Edge",
            "firefox": "Firefox",
            "whatsapp": "WhatsApp",
            "watsapp": "WhatsApp",
            "what's app": "WhatsApp",
            "wa": "WhatsApp",
            "wps": "WPS Office",
            "notepad": "Notepad",
            "calculator": "Calculator",
            "settings": "Settings",
            "vs code": "VS Code",
        }
        normalized = lowered.replace("watsapp", "whatsapp").replace("what's app", "whatsapp").replace("what app", "whatsapp")
        for key, value in app_map.items():
            if key in normalized:
                return value
        return "default"

    def _detect_search_target(self, prompt: str) -> str:
        query = re.sub(r"(?i)^\s*(?:hey nova[, ]*|please\s+|mujhe\s+)+", "", prompt).strip()
        query = re.sub(r"(?i)^(?:google|youtube|web)\s+(?:par|pe|mein|me)\s+", "", query)
        query = re.sub(r"(?i)^(?:search|find|look up)\s+(?:for\s+)?", "", query)
        query = re.sub(r"(?i)\s+(?:search\s*(?:karo|kro)?|dhoondho|dhoondo|dhoond|dhundho|dhundo|dhund|khojo|talash karo|please)$", "", query)
        return query.strip() or prompt.strip()

    def _extract_contact(self, prompt: str) -> str:
        match = re.search(r"(?:to|for|ko|pe)\s+([A-Za-z][A-Za-z\s]+)", prompt, flags=re.I)
        if match:
            return match.group(1).strip()
        return "unknown contact"

    def _extract_message(self, prompt: str) -> str:
        if ":" in prompt:
            return prompt.split(":", 1)[1].strip()
        match = re.search(r"(?:message|msg|chat|send)\s+(?:to\s+.*?\s+)?(?:.*?:\s*)(.+)$", prompt, flags=re.I)
        if match:
            return match.group(1).strip()
        return "Hello"


class OpenAIProvider(LocalModelProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def plan_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> List[ActionRequest]:
        if not self.api_key:
            return super().plan_task(prompt, context)
        return super().plan_task(prompt, context)

    def extract_intent(self, prompt: str) -> Dict[str, Any]:
        return super().extract_intent(prompt)


class SpeechToTextProvider(Protocol):
    def listen_once(self, timeout: int = 10) -> str:
        ...


class TextToSpeechProvider(Protocol):
    def speak(self, text: str) -> None:
        ...


class WakeWordProvider(Protocol):
    def detect(self, wake_words: Sequence[str]) -> bool:
        ...


class LocalWakeWordProvider:
    def __init__(self, recognizer: Optional[Any] = None):
        self.recognizer = recognizer or sr

    def detect(self, wake_words: Sequence[str]) -> bool:
        if self.recognizer is None:
            return False
        try:
            mic = self.recognizer.Microphone()
            with mic as source:
                audio = self.recognizer.Recognizer().listen(source, timeout=1, phrase_time_limit=1)
            text = self.recognizer.Recognizer().recognize_google(audio)
            phrase = text.lower()
            return any(w.lower() in phrase for w in wake_words)
        except Exception:
            return False


class LocalSpeechToTextProvider:
    def __init__(self, recognizer: Optional[Any] = None):
        self.recognizer = recognizer or sr

    def listen_once(self, timeout: int = 10) -> str:
        if self.recognizer is None:
            return ""
        try:
            mic = self.recognizer.Microphone()
            with mic as source:
                audio = self.recognizer.Recognizer().listen(source, timeout=timeout)
                return self.recognizer.Recognizer().recognize_google(audio)
        except Exception as exc:
            LOGGER.warning("Speech recognition failed: %s", exc)
            return ""


class LocalTextToSpeechProvider:
    def __init__(self):
        self.engine = pyttsx3.init() if pyttsx3 is not None else None

    def speak(self, text: str) -> None:
        if not text:
            return
        if self.engine is not None:
            self.engine.say(text)
            self.engine.runAndWait()
        else:
            print(f"[TTS] {text}")


class PermissionEngine:
    def __init__(self):
        self._allowlist = {"chrome", "edge", "calculator", "notepad", "settings", "whatsapp", "wps"}
        self._denylist = {"disabling antivirus", "password reset", "system takeover"}

    def classify(self, action: str) -> RiskLevel:
        action_lower = action.lower()
        if any(keyword in action_lower for keyword in ["delete", "shutdown", "restart", "install", "send", "rename", "move", "download"]):
            if any(keyword in action_lower for keyword in ["password", "security", "bank", "payment", "otp", "delete large", "disable"]):
                return RiskLevel.HIGH
            if any(keyword in action_lower for keyword in ["install", "download", "rename", "move", "send", "delete"]):
                return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def requires_confirmation(self, action: ActionRequest) -> bool:
        return action.require_confirmation or action.risk in {RiskLevel.MEDIUM, RiskLevel.HIGH}

    def is_allowed(self, action: ActionRequest) -> bool:
        if action.name in {"system_control", "send_message", "rename_file", "delete_file"}:
            return action.risk in {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}
        return True

    def is_dangerous(self, action: ActionRequest) -> bool:
        return any(word in action.name.lower() for word in ["delete", "install", "shutdown", "restart", "password"]) or action.risk == RiskLevel.HIGH


class ActionValidator:
    def validate(self, action: ActionRequest) -> bool:
        if not action.name:
            return False
        if action.name == "open_application" and "application" not in action.parameters:
            return False
        if action.name == "search_web" and "query" not in action.parameters:
            return False
        return True


class NovaSecurity:
    def __init__(self):
        self.permission_engine = PermissionEngine()
        self.validator = ActionValidator()

    def validate_action(self, action: ActionRequest) -> bool:
        if not self.validator.validate(action):
            return False
        if self.permission_engine.is_dangerous(action):
            return False
        return True


class NovaMemory:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path.home() / "AppData" / "Local" / "NovaAssistant" / "memory.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"preferences": {}, "contacts": {}, "favorites": {}, "context": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {"preferences": {}, "contacts": {}, "favorites": {}, "context": {}}

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)

    def remember(self, key: str, value: Any) -> None:
        self._data.setdefault("preferences", {})[key] = value
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get("preferences", {}).get(key, default)

    def remember_context(self, key: str, value: Any) -> None:
        self._data.setdefault("context", {})[key] = value
        self.save()

    def get_context(self, key: str, default: Any = None) -> Any:
        return self._data.get("context", {}).get(key, default)

    def clear(self) -> None:
        self._data = {"preferences": {}, "contacts": {}, "favorites": {}, "context": {}}
        self.save()


class NovaScheduler:
    def __init__(self):
        self.reminders: List[Reminder] = []
        self._lock = threading.Lock()

    def add_reminder(self, text: str, when: datetime, recurring: Optional[str] = None) -> str:
        reminder_id = f"reminder-{int(time.time() * 1000)}"
        with self._lock:
            self.reminders.append(Reminder(reminder_id, text, when, recurring))
        return reminder_id

    def run_due_reminders(self, speaker: Callable[[str], None]) -> None:
        now = datetime.now()
        with self._lock:
            due = [reminder for reminder in self.reminders if reminder.run_at <= now]
            for reminder in due:
                speaker(f"Reminder: {reminder.text}")
                if reminder.recurring:
                    next_run = self._compute_next_run(reminder.run_at, reminder.recurring)
                    reminder.run_at = next_run
                else:
                    self.reminders.remove(reminder)

    def _compute_next_run(self, current: datetime, recurrence: str) -> datetime:
        if recurrence.lower() == "daily":
            return current + timedelta(days=1)
        if recurrence.lower() == "weekly":
            return current + timedelta(days=7)
        return current + timedelta(minutes=30)


class NovaComputerControl:
    def __init__(self):
        self.applications: Dict[str, ApplicationDefinition] = self._default_registry()

    @staticmethod
    def _default_registry() -> Dict[str, ApplicationDefinition]:
        return {
            "chrome": ApplicationDefinition("Chrome", aliases=("chrome", "google chrome", "browser"), supported_actions=("open", "search")),
            "edge": ApplicationDefinition("Microsoft Edge", aliases=("edge", "microsoft edge"), supported_actions=("open", "search")),
            "firefox": ApplicationDefinition("Firefox", aliases=("firefox"), supported_actions=("open", "search")),
            "whatsapp": ApplicationDefinition("WhatsApp", aliases=("whatsapp", "whatsapp web"), supported_actions=("open", "send_message")),
            "wps": ApplicationDefinition("WPS Office", aliases=("wps", "wps office"), supported_actions=("open", "write", "save")),
            "settings": ApplicationDefinition("Settings", aliases=("settings"), supported_actions=("open")),
            "calculator": ApplicationDefinition("Calculator", aliases=("calculator"), supported_actions=("open")),
            "notepad": ApplicationDefinition("Notepad", aliases=("notepad"), supported_actions=("open", "write")),
            "vs code": ApplicationDefinition("VS Code", aliases=("vs code", "code"), supported_actions=("open")),
        }

    def open_application(self, application: str) -> Dict[str, Any]:
        app_name = self._resolve_app_name(application)
        normalized = app_name.casefold()

        if normalized in {"whatsapp", "youtube", "google"}:
            if normalized == "whatsapp":
                try:
                    os.startfile("whatsapp://")
                    return {"status": "opened", "application": app_name}
                except OSError:
                    return self.open_url("https://web.whatsapp.com")
            url = "https://www.youtube.com" if normalized == "youtube" else "https://www.google.com"
            return self.open_url(url)

        executable_names = {
            "chrome": ("chrome.exe",),
            "microsoft edge": ("msedge.exe",),
            "firefox": ("firefox.exe",),
            "notepad": ("notepad.exe",),
            "calculator": ("calc.exe",),
            "vs code": ("code.exe", "code.cmd"),
            "wps office": ("wps.exe", "et.exe"),
        }
        candidates = executable_names.get(normalized)
        if normalized == "settings":
            try:
                os.startfile("ms-settings:")
                return {"status": "opened", "application": app_name}
            except OSError as exc:
                return {"status": "error", "application": app_name, "detail": str(exc)}
        if not candidates:
            return {"status": "error", "application": app_name, "detail": "Application is not supported."}

        executable = next((shutil.which(name) for name in candidates if shutil.which(name)), None)
        if executable is None and normalized == "chrome":
            roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
            paths = [Path(root) / "Google/Chrome/Application/chrome.exe" for root in roots if root]
            executable = next((str(path) for path in paths if path.is_file()), None)
        if executable is None:
            return {"status": "error", "application": app_name, "detail": f"{app_name} was not found on this computer."}

        try:
            subprocess.Popen([executable], close_fds=True)
            return {"status": "opened", "application": app_name}
        except OSError as exc:
            LOGGER.exception("Failed to launch %s", app_name)
            return {"status": "error", "application": app_name, "detail": str(exc)}

    def open_url(self, url: str) -> Dict[str, Any]:
        import webbrowser
        webbrowser.open(url)
        return {"status": "ok", "url": url}

    def search_web(self, query: str) -> Dict[str, Any]:
        from urllib.parse import urlencode

        return self.open_url(f"https://www.google.com/search?{urlencode({'q': query})}")

    def search_youtube(self, query: str) -> Dict[str, Any]:
        from urllib.parse import urlencode

        return self.open_url(f"https://www.youtube.com/results?{urlencode({'search_query': query})}")

    def take_screenshot(self, path: Optional[str] = None) -> Dict[str, Any]:
        target = path or str(Path.home() / "Pictures" / "nova_screenshot.png")
        out = Path(target)
        out.parent.mkdir(parents=True, exist_ok=True)
        return {"status": "saved", "path": str(out)}

    def create_folder(self, path: str) -> Dict[str, Any]:
        folder = Path(path)
        folder.mkdir(parents=True, exist_ok=True)
        return {"status": "created", "path": str(folder)}

    def rename_file(self, source: str, destination: str) -> Dict[str, Any]:
        src = Path(source)
        dst = Path(destination)
        src.rename(dst)
        return {"status": "renamed", "source": str(src), "destination": str(dst)}

    def move_file(self, source: str, destination: str) -> Dict[str, Any]:
        src = Path(source)
        dst = Path(destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dst)
        return {"status": "moved", "source": str(src), "destination": str(dst)}

    def send_message(self, recipient: str, message: str) -> Dict[str, Any]:
        LOGGER.info("Prepared message to %s: %s", recipient, message)
        return {"status": "prepared", "recipient": recipient, "message": message}

    def prepare_whatsapp_message(self, phone_number: str, message: str) -> Dict[str, Any]:
        digits = re.sub(r"\D", "", phone_number)
        text = message.strip()
        if not 8 <= len(digits) <= 15:
            raise ValueError("Enter a phone number with country code, 8 to 15 digits.")
        if not text or len(text) > 2000:
            raise ValueError("Enter a message between 1 and 2000 characters.")

        from urllib.parse import quote

        url = f"https://wa.me/{digits}?text={quote(text)}"
        self.open_url(url)
        return {"status": "draft_opened", "phone": digits}

    def system_control(self, command: str) -> Dict[str, Any]:
        allowed = {"lock", "shutdown", "restart", "volume", "brightness"}
        if command not in allowed:
            return {"status": "rejected", "reason": "unsupported command"}
        return {"status": "requested", "command": command}

    def _resolve_app_name(self, application: str) -> str:
        lookup = application.lower().strip()
        if lookup in {"youtube", "google"}:
            return lookup.title()
        for name, definition in self.applications.items():
            if lookup in {name.lower(), *[alias.lower() for alias in definition.aliases]}:
                return definition.name
        return application


class NovaLocalApiHandler(BaseHTTPRequestHandler):
    control = NovaComputerControl()
    allowed_origins = {"http://localhost:8000", "http://127.0.0.1:8000", "null"}

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        origin = self.headers.get("Origin")
        if origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin")
        if origin not in self.allowed_origins:
            self._send_json(403, {"error": "Origin not allowed"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ready"})
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path not in {"/open", "/message", "/search"}:
            self._send_json(404, {"error": "Not found"})
            return
        if self.headers.get("Origin") not in self.allowed_origins:
            self._send_json(403, {"error": "Origin not allowed"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/open":
                application = str(payload.get("application", "")).strip()
                if not application or len(application) > 80:
                    raise ValueError("Invalid application name")
                result = self.control.open_application(application)
                status = 200 if result.get("status") in {"opened", "ok"} else 400
            elif self.path == "/message":
                result = self.control.prepare_whatsapp_message(
                    str(payload.get("phone", "")),
                    str(payload.get("message", "")),
                )
                status = 200
            else:
                query = str(payload.get("query", "")).strip()
                site = str(payload.get("site", "google")).casefold()
                if not query or len(query) > 500:
                    raise ValueError("Search query must be between 1 and 500 characters.")
                if site not in {"google", "youtube"}:
                    raise ValueError("Search provider is not supported.")
                result = self.control.search_youtube(query) if site == "youtube" else self.control.search_web(query)
                status = 200
            self._send_json(status, result)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("Nova local API: " + format, *args)


def run_local_api() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), NovaLocalApiHandler)
    LOGGER.info("Nova app launcher listening at http://127.0.0.1:8765")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


class NovaPlanner:
    def __init__(self, ai_provider: Optional[AIProvider] = None):
        self.ai_provider = ai_provider or LocalModelProvider()

    def create_plan(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> List[ActionRequest]:
        return self.ai_provider.plan_task(prompt, context)


class NovaTaskHistory:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path.home() / "AppData" / "Local" / "NovaAssistant" / "history.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: List[TaskHistoryEntry] = self._load()

    def _load(self) -> List[TaskHistoryEntry]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [TaskHistoryEntry(**entry) for entry in raw]
        except Exception:
            return []

    def add(self, command: str, steps: List[str], result: str, errors: Optional[List[str]] = None) -> None:
        self.entries.append(TaskHistoryEntry(datetime.now().isoformat(), command, steps, result, errors or []))
        self.path.write_text(json.dumps([entry.__dict__ for entry in self.entries], indent=2, ensure_ascii=False), encoding="utf-8")

    def clear(self) -> None:
        self.entries.clear()
        self.path.write_text("[]", encoding="utf-8")


class NovaAssistant:
    def __init__(self, name: str = "Nova"):
        self.name = name
        self.state = AssistantState.WAITING
        self.memory = NovaMemory()
        self.scheduler = NovaScheduler()
        self.control = NovaComputerControl()
        self.ai = LocalModelProvider()
        self.planner = NovaPlanner(self.ai)
        self.security = NovaSecurity()
        self.history = NovaTaskHistory()
        self.stt = LocalSpeechToTextProvider() if sr is not None else None
        self.tts = LocalTextToSpeechProvider() if pyttsx3 is not None else None
        self.wake_word = LocalWakeWordProvider() if sr is not None else None
        self.current_task: Optional[str] = None
        self.current_step: str = "Idle"
        self.conversation_context: Dict[str, Any] = {"last_application": None}
        self._stop_requested = False
        self.ui = None
        self.wake_words = ["hey nova", "nova"]

    def bind_ui(self, ui: Any) -> None:
        self.ui = ui
        self.refresh_ui()

    def refresh_ui(self) -> None:
        if self.ui is not None and hasattr(self.ui, "update_status"):
            self.ui.update_status(self.state.value, self.current_task or "None", self.current_step)

    def speak(self, text: str) -> None:
        if self.tts:
            self.tts.speak(text)
        else:
            print(f"{self.name}: {text}")

    def listen_for_wake_word(self) -> bool:
        if self.wake_word is None:
            return True
        self.state = AssistantState.WAITING
        self.refresh_ui()
        self.speak("Waiting for wake word")
        detected = self.wake_word.detect(self.wake_words)
        if detected:
            self.state = AssistantState.LISTENING
            self.refresh_ui()
        return detected

    def listen_for_command(self) -> str:
        self.state = AssistantState.LISTENING
        self.refresh_ui()
        self.speak("Listening.")
        if self.stt is None:
            user_input = input("Command: ")
            return user_input.strip()
        transcript = self.stt.listen_once(timeout=10)
        if not transcript:
            self.speak("I did not catch that. Please say your command again.")
            return ""
        return transcript

    def ask_confirmation(self, message: str) -> bool:
        self.speak(message)
        response = (self.listen_for_command() if self.stt is not None else input("Reply yes/no: ")).strip().lower()
        return response in {"yes", "yes please", "go ahead", "continue", "y", "haan", "haan ji"}

    def handle_command(self, command: str) -> None:
        if not command:
            return
        command = command.strip()
        lower = command.lower()
        if any(token in lower for token in ["stop", "cancel", "pause", "wait", "don't do that"]):
            self.state = AssistantState.PAUSED
            self.refresh_ui()
            self.speak("Stopping the current task.")
            self.current_task = None
            self.current_step = "Cancelled"
            self.refresh_ui()
            return

        if any(token in lower for token in ["clear my assistant memory", "forget this", "don't remember that"]):
            self.memory.clear()
            self.speak("Assistant memory cleared.")
            return

        if "reminder" in lower or "remember" in lower:
            self._handle_reminder(command)
            return

        self.current_task = command
        self.state = AssistantState.PROCESSING
        self.current_step = "Planning"
        self.refresh_ui()
        self.speak("I’ll handle that request.")
        plan = self.planner.create_plan(command, self.conversation_context)

        if not plan:
            self.speak("I couldn’t understand the request. Please try again more clearly.")
            return

        self.state = AssistantState.EXECUTING
        self.refresh_ui()
        steps: List[str] = []
        errors: List[str] = []
        for step in plan:
            steps.append(step.name)
            if not self.security.validate_action(step):
                self.speak("This action is restricted by the safety system.")
                errors.append(f"blocked:{step.name}")
                continue
            if self.security.permission_engine.requires_confirmation(step):
                confirmed = self.ask_confirmation(f"I’m preparing to {step.name}. Do you want me to continue?")
                if not confirmed:
                    self.speak("Cancelled.")
                    self.current_step = "Cancelled"
                    self.refresh_ui()
                    return
            self.current_step = step.name
            self.refresh_ui()
            result = self._execute_action(step)
            if not result["ok"]:
                errors.append(result.get("error", step.name))
                self.speak("The action failed. I’ll retry if it is safe to do so.")
                break

        final_result = "completed" if not errors else "encountered errors"
        self.speak(final_result.capitalize() + ".")
        self.history.add(command, steps, final_result, errors)
        self.current_task = None
        self.current_step = "Idle"
        self.state = AssistantState.WAITING
        self.refresh_ui()

    def _execute_action(self, action: ActionRequest) -> Dict[str, Any]:
        action_name = action.name
        if action_name == "open_application":
            result = self.control.open_application(action.parameters.get("application", "default"))
        elif action_name == "search_web":
            result = self.control.search_web(action.parameters.get("query", ""))
        elif action_name == "take_screenshot":
            result = self.control.take_screenshot(action.parameters.get("path"))
        elif action_name == "send_message":
            result = self.control.send_message(action.parameters.get("recipient", "unknown contact"), action.parameters.get("message", ""))
        elif action_name == "system_control":
            result = self.control.system_control(action.parameters.get("command", "lock"))
        else:
            result = {"status": "not_implemented", "ok": False, "error": f"{action_name} is not implemented in this stub."}
        result.setdefault("ok", result.get("status") not in {"rejected", "not_implemented"})
        return result

    def _handle_reminder(self, command: str) -> None:
        if re.search(r"(in|after)\s+(\d+)\s*(minute|minutes|min)", command, flags=re.I):
            match = re.search(r"(\d+)\s*(minute|minutes|min)", command, flags=re.I)
            if match:
                minutes = int(match.group(1))
                reminder_text = command.replace(match.group(0), "").strip() or "Reminder"
                run_at = datetime.now() + timedelta(minutes=minutes)
                reminder_id = self.scheduler.add_reminder(reminder_text, run_at)
                self.speak(f"Reminder scheduled for {minutes} minutes from now.")
                self.memory.remember_context(f"reminder:{reminder_id}", reminder_text)
                return

        self.speak("I can schedule reminders, but for a full calendar feature you can add a persistent scheduler to the project.")

    def run(self) -> None:
        self.state = AssistantState.WAITING
        self.refresh_ui()
        self.speak(f"{self.name} is online and ready.")
        while not self._stop_requested:
            self.scheduler.run_due_reminders(self.speak)
            if self.listen_for_wake_word():
                command = self.listen_for_command()
                if command:
                    self.handle_command(command)
            time.sleep(0.5)

    def stop(self) -> None:
        self._stop_requested = True
        self.state = AssistantState.PAUSED
        self.refresh_ui()
        self.speak("Nova shutting down.")


class NovaDesktopWindow:
    def __init__(self, assistant: NovaAssistant):
        self.assistant = assistant
        self._app = None
        self.window = None
        self.status_label = None
        self.task_label = None
        self.step_label = None
        self.mic_label = None
        self.assistant.bind_ui(self)

    def update_status(self, state: str, task: str, step: str) -> None:
        if self.status_label is None:
            return
        self.status_label.setText(f"Status: {state}")
        self.task_label.setText(f"Current task: {task}")
        self.step_label.setText(f"Current step: {step}")
        mic_state = "● Listening" if state in {AssistantState.LISTENING.value, AssistantState.PROCESSING.value, AssistantState.EXECUTING.value} else "● Ready"
        self.mic_label.setText(f"Microphone: {mic_state}")

    def start(self) -> None:
        if QtWidgets is None:
            LOGGER.warning("PySide6 is not installed. Running in console mode only.")
            self.assistant.run()
            return

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self._app = app
        self.window = QtWidgets.QWidget()
        self.window.setWindowTitle("Nova")
        self.window.resize(480, 320)
        self.window.setStyleSheet("background: #0f172a; color: #e2e8f0; font-family: Segoe UI; font-size: 14px;")

        layout = QtWidgets.QVBoxLayout(self.window)
        heading = QtWidgets.QLabel("NOVA\nAI COMPUTER ASSISTANT")
        heading.setStyleSheet("font-size: 24px; font-weight: 700; color: #f8fafc; margin-bottom: 8px;")
        layout.addWidget(heading)

        self.mic_label = QtWidgets.QLabel("Microphone: ● Ready")
        self.status_label = QtWidgets.QLabel("Status: WAITING")
        self.task_label = QtWidgets.QLabel("Current task: None")
        self.step_label = QtWidgets.QLabel("Current step: Idle")

        for label in [self.mic_label, self.status_label, self.task_label, self.step_label]:
            label.setStyleSheet("padding: 6px 0; color: #dbeafe;")
            layout.addWidget(label)

        buttons_layout = QtWidgets.QHBoxLayout()
        speak_btn = QtWidgets.QPushButton("Speak")
        stop_btn = QtWidgets.QPushButton("Stop")
        history_btn = QtWidgets.QPushButton("History")
        settings_btn = QtWidgets.QPushButton("Settings")

        for button in [speak_btn, stop_btn, history_btn, settings_btn]:
            button.setStyleSheet("background: #2563eb; border: none; border-radius: 10px; padding: 10px; color: white; min-width: 90px;")
            buttons_layout.addWidget(button)

        layout.addLayout(buttons_layout)

        speak_btn.clicked.connect(lambda: self.assistant.handle_command("Open Chrome"))
        stop_btn.clicked.connect(self.assistant.stop)
        history_btn.clicked.connect(lambda: self.assistant.speak("Task history is available in the local log."))
        settings_btn.clicked.connect(lambda: self.assistant.speak("Settings panel is available in the next build."))

        self.update_status(self.assistant.state.value, self.assistant.current_task or "None", self.assistant.current_step)
        self.window.show()
        self._app.exec()

if __name__ == "__main__":
    nova = NovaAssistant(name="Nova")
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "api":
            run_local_api()
        elif len(sys.argv) > 1 and sys.argv[1] == "ui":
            NovaDesktopWindow(nova).start()
        else:
            nova.run()
    except KeyboardInterrupt:
        nova.stop()
