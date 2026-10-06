# Nova AI Assistant

Nova is a Windows-first AI desktop assistant starter built around the requirements in the master brief. It provides a safe action framework, a command planner, local memory and scheduling, optional voice/TTS integration, and a console-first desktop shell.

## Features

- Wake-word ready architecture with microphone support
- Local AI intent extraction and task planning
- Permission and confirmation gating for risky actions
- Computer control layer with application and browser abstraction
- Local memory and reminder scheduling
- Task history and reversible starter controls
- Windows-friendly UI scaffold using PySide6 when available

## Files

- `jarvis.py` — main assistant implementation
- `requirements.txt` — dependency list

## Run

Start the local Windows app launcher in one terminal:

```powershell
python "C:\Users\rp550ws\OneDrive\Desktop\jarvis.py" api
```

Keep the dashboard served at `http://localhost:8000/index.html` in your browser. The dashboard sends supported app-open commands to the local launcher at `127.0.0.1:8765`.

Common Hinglish commands include `Chrome khol do`, `YouTube chala do`, and `Google pe Bihar Polytechnic syllabus dhoondo`. Message commands can address a contact saved in Contacts, for example `Asif ko WhatsApp message bhejo ki main raste mein hoon`.

Add a name and country-code phone number from the dashboard's Contacts button. These allowed contacts stay in this browser only. Then enter `WhatsApp message to contact name: message text`; Nova opens a draft for review, and you press Send in WhatsApp.

To run the voice assistant in console mode instead, use:

```bash
python "C:\Users\rp550ws\OneDrive\Desktop\jarvis.py"
```

To launch the Qt desktop UI shell, use:

```bash
python "C:\Users\rp550ws\OneDrive\Desktop\jarvis.py" ui
```

## Notes

This is an MVP/starter implementation designed to be extended with real Windows automation, authenticated credential storage, and production-safe AI provider integrations.
