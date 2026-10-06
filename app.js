const micStatus = document.getElementById('micStatus');
const assistantStatus = document.getElementById('assistantStatus');
const currentTask = document.getElementById('currentTask');
const commandText = document.getElementById('commandText');
const cpuValue = document.getElementById('cpuValue');
const ramValue = document.getElementById('ramValue');
const cpuBar = document.getElementById('cpuBar');
const ramBar = document.getElementById('ramBar');
const wakeWordState = document.getElementById('wakeWordState');
const currentStep = document.getElementById('currentStep');
const taskTitle = document.getElementById('taskTitle');
const commandInput = document.getElementById('commandInput');
const runCommandBtn = document.getElementById('runCommandBtn');
const contactsDialog = document.getElementById('contactsDialog');
const contactsList = document.getElementById('contactsList');
const contactsStatus = document.getElementById('contactsStatus');
const contactForm = document.getElementById('contactForm');

const statusMap = {
  ready: 'Ready',
  listening: 'Listening',
  processing: 'Processing',
  executing: 'Executing',
  paused: 'Paused'
};

let listening = true;
let allowedContacts = loadAllowedContacts();

function loadAllowedContacts() {
  try {
    const contacts = JSON.parse(localStorage.getItem('novaAllowedContacts') || '[]');
    return Array.isArray(contacts) ? contacts.filter((contact) => contact.name && contact.phone) : [];
  } catch {
    return [];
  }
}

function saveAllowedContacts() {
  try {
    localStorage.setItem('novaAllowedContacts', JSON.stringify(allowedContacts));
    return true;
  } catch {
    contactsStatus.textContent = 'Could not save contacts in this browser.';
    return false;
  }
}

function renderAllowedContacts() {
  contactsList.replaceChildren();
  for (const contact of allowedContacts) {
    const item = document.createElement('li');
    const details = document.createElement('div');
    details.className = 'contact-details';
    const name = document.createElement('strong');
    name.textContent = contact.name;
    const phone = document.createElement('span');
    phone.textContent = contact.phone;
    const remove = document.createElement('button');
    remove.className = 'contact-remove';
    remove.type = 'button';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => {
      allowedContacts = allowedContacts.filter((entry) => entry !== contact);
      if (saveAllowedContacts()) renderAllowedContacts();
    });
    details.append(name, phone);
    item.append(details, remove);
    contactsList.append(item);
  }
}

document.getElementById('contactsButton').addEventListener('click', () => {
  contactsStatus.textContent = '';
  renderAllowedContacts();
  contactsDialog.showModal();
});

document.getElementById('closeContacts').addEventListener('click', () => contactsDialog.close());

contactForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const name = document.getElementById('contactName').value.trim();
  const phone = document.getElementById('contactPhone').value.replace(/\D/g, '');
  if (!name || phone.length < 8 || phone.length > 15) {
    contactsStatus.textContent = 'Enter a name and a valid country-code phone number.';
    return;
  }

  allowedContacts = allowedContacts.filter((contact) => contact.name.toLowerCase() !== name.toLowerCase());
  allowedContacts.push({ name, phone });
  if (saveAllowedContacts()) {
    contactForm.reset();
    contactsStatus.textContent = `${name} is now allowed.`;
    renderAllowedContacts();
  }
});

function updateMetrics() {
  const cpu = Math.floor(18 + Math.random() * 24);
  const ram = Math.floor(32 + Math.random() * 32);

  cpuValue.textContent = `${cpu}%`;
  ramValue.textContent = `${ram}%`;
  cpuBar.style.width = `${cpu}%`;
  ramBar.style.width = `${ram}%`;
}

function setState(state) {
  assistantStatus.textContent = statusMap[state] || 'Ready';
  micStatus.textContent = state === 'listening' || state === 'processing' || state === 'executing'
    ? '● Listening'
    : '● Ready';
  micStatus.classList.toggle('online-text', state !== 'paused');

  if (state === 'processing') {
    currentTask.textContent = 'Task in progress';
    currentStep.textContent = 'Analyzing request';
    taskTitle.textContent = 'Prepare assistant action';
  }

  if (state === 'executing') {
    currentStep.textContent = 'Opening application';
  }

  if (state === 'paused') {
    currentTask.textContent = 'Cancelled';
    currentStep.textContent = 'Idle';
    taskTitle.textContent = 'No active task';
  }

  if (state === 'ready') {
    currentTask.textContent = 'None';
    currentStep.textContent = 'Idle';
    taskTitle.textContent = 'Send WhatsApp message to Asif';
  }
}

async function openApplication(application) {
  setState('executing');
  currentTask.textContent = `Open ${application}`;
  currentStep.textContent = 'Connecting to Windows app launcher';
  taskTitle.textContent = `Open ${application}`;
  wakeWordState.textContent = 'Active';

  try {
    const response = await fetch('http://127.0.0.1:8765/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ application })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || result.error || 'Windows could not open that app.');
    currentStep.textContent = `${application} opened`;
    assistantStatus.textContent = 'Ready';
    commandText.textContent = `"Opened ${application}."`;
  } catch (error) {
    assistantStatus.textContent = 'Error';
    currentTask.textContent = `Could not open ${application}`;
    currentStep.textContent = error.message.toLowerCase().includes('fetch')
      ? 'Start Nova local launcher: python jarvis.py api'
      : error.message;
    taskTitle.textContent = `Could not open ${application}`;
  }
}

async function prepareWhatsAppMessage(phone, message) {
  setState('executing');
  currentTask.textContent = 'Prepare WhatsApp message';
  currentStep.textContent = 'Opening message draft';
  taskTitle.textContent = 'Review message in WhatsApp';

  try {
    const response = await fetch('http://127.0.0.1:8765/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, message })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || result.error || 'Could not prepare the message.');
    currentStep.textContent = 'Draft opened; review it and tap Send in WhatsApp';
    assistantStatus.textContent = 'Ready';
    commandText.textContent = '"WhatsApp draft is ready for your review."';
  } catch (error) {
    assistantStatus.textContent = 'Error';
    currentTask.textContent = 'Message draft failed';
    currentStep.textContent = error.message;
    taskTitle.textContent = 'Could not prepare message';
  }
}

async function searchWeb(query, site) {
  setState('executing');
  currentTask.textContent = `Search ${site === 'youtube' ? 'YouTube' : 'Google'}`;
  currentStep.textContent = 'Opening search results';
  taskTitle.textContent = `Search: ${query}`;

  try {
    const response = await fetch('http://127.0.0.1:8765/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, site })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || result.error || 'Could not search the web.');
    currentStep.textContent = 'Search results opened';
    assistantStatus.textContent = 'Ready';
  } catch (error) {
    assistantStatus.textContent = 'Error';
    currentStep.textContent = error.message;
    taskTitle.textContent = 'Search failed';
  }
}

function processCommand(rawText) {
  const text = rawText.trim();
  if (!text) return;

  const normalized = text.toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/[.,!?]/g, ' ')
    .replace(/watsapp|what'?s app|whats app|what app/g, 'whatsapp')
    .replace(/\s+/g, ' ')
    .trim();
  commandText.textContent = `"${text}"`;

  if (/\b(stop|cancel|pause)\b/.test(normalized)) {
    setState('paused');
    wakeWordState.textContent = 'Standby';
    currentTask.textContent = 'Cancelled';
    currentStep.textContent = 'Stopping current task';
    return;
  }

  if (/\b(message|msg|sms|text|bhej|bhejo|bhejna|likho)\b/.test(normalized)) {
    const bodyMatch = text.match(/:\s*(.+)$|\b(?:saying|that|ki)\s+(.+)$/i);
    const message = bodyMatch ? (bodyMatch[1] || bodyMatch[2]).trim() : '';
    let recipientText = bodyMatch ? text.slice(0, bodyMatch.index) : text;
    recipientText = recipientText
      .replace(/^(?:hey nova[, ]*|please\s+|mujhe\s+)+/i, '')
      .replace(/^(?:whatsapp|wa)\s+(?:par|pe)\s+/i, '')
      .replace(/^(?:please\s+)?(?:send|bhejo?|bhej do)\s+/i, '')
      .replace(/^(?:whatsapp\s+)?(?:message|msg|sms|text)\s+(?:(?:to|for|ko|pe)\s+)?/i, '')
      .trim();
    const recipientFirst = recipientText.match(/^(.+?)\s+(?:ko|ke liye)\s+(?:whatsapp\s+)?(?:message|msg|sms|text|bhej(?:o|na)?|likho)(?:\s+(?:bhejo|bhej do|karo|kar do))?$/i);
    if (recipientFirst) recipientText = recipientFirst[1].trim();
    recipientText = recipientText
      .replace(/\s+(?:whatsapp\s+)?(?:message|msg|sms|text|bhej(?:o|na)?|likho)(?:\s+(?:bhejo|bhej do|karo|kar do))?$/i, '')
      .trim();
    const phoneMatch = recipientText.match(/\+?\d(?:[\d\s().-]{6,}\d)/);
    const savedContact = allowedContacts.find((contact) => contact.name.toLowerCase() === recipientText.toLowerCase());
    const phone = phoneMatch ? phoneMatch[0] : savedContact?.phone;
    if (!message) {
      setState('processing');
      currentTask.textContent = 'Message not sent';
      currentStep.textContent = 'Add message text after a colon.';
      taskTitle.textContent = 'Need recipient number and message';
      return;
    }
    if (!phone) {
      setState('processing');
      currentTask.textContent = 'Message not sent';
      currentStep.textContent = recipientText
        ? `Add ${recipientText} in Contacts first.`
        : 'Add a recipient number or allowed contact name.';
      taskTitle.textContent = 'Recipient is not allowed';
      return;
    }
    prepareWhatsAppMessage(phone, message);
    return;
  }

  const searchIntent = /\b(search|find|look up|dhoond|dhoondo|dhoondho|dhund|dhundo|dhundho|khojo|talash)\b/.test(normalized)
    || /\b(?:google|youtube)\s+(?:par|pe|mein|me)\b/.test(normalized);
  if (searchIntent) {
    let query = normalized.replace(/^(?:hey nova[, ]*|please\s+|mujhe\s+)+/, '');
    const searchVerb = query.match(/\b(?:search|find|look up|dhoond|dhoondo|dhoondho|dhund|dhundo|dhundho|khojo|talash)\b\s+(?:for\s+)?(.+)$/);
    if (searchVerb) {
      query = searchVerb[1];
    } else {
      query = query.replace(/^(?:(?:google|youtube|web)\s+(?:par|pe|mein|me)\s+)/, '');
    }
    query = query
      .replace(/^(?:google|youtube)\s+(?:for|ke liye)\s+/, '')
      .replace(/\s+(?:search\s*)?(?:karo|kro|kar do|dhoond|dhoondo|dhoondho|dhund|dhundo|dhundho|khojo|please)$/i, '')
      .trim();
    if (!query) {
      setState('processing');
      currentTask.textContent = 'Search not started';
      currentStep.textContent = 'Tell Nova what to search for.';
      taskTitle.textContent = 'Need a search query';
      return;
    }
    searchWeb(query, normalized.includes('youtube') ? 'youtube' : 'google');
    return;
  }

  const launchPhrase = /\b(open|launch|start|run|khol|kholo|kholna|chala|chalao|khulwao)\b|\b(?:open|launch|start|chala|khol)\s+(?:karo|kro|do|de)\b/.test(normalized);
  const appTargets = [
    { name: 'WhatsApp', aliases: ['whatsapp'] },
    { name: 'Chrome', aliases: ['google chrome', 'chrome'] },
    { name: 'Microsoft Edge', aliases: ['microsoft edge', 'edge'] },
    { name: 'Firefox', aliases: ['firefox'] },
    { name: 'Notepad', aliases: ['notepad'] },
    { name: 'Calculator', aliases: ['calculator', 'calc'] },
    { name: 'Settings', aliases: ['settings'] },
    { name: 'VS Code', aliases: ['vs code', 'visual studio code'] },
    { name: 'WPS Office', aliases: ['wps office', 'wps'] },
    { name: 'YouTube', aliases: ['youtube'] },
    { name: 'Google', aliases: ['google'] }
  ];
  const target = appTargets.find((app) => app.aliases.some((alias) => normalized.includes(alias))
    && (launchPhrase || app.name === 'WhatsApp'));
  if (target) {
    openApplication(target.name);
    return;
  }

  if (normalized.includes('reminder') || normalized.includes('yaad') || normalized.includes('remember')) {
    setState('processing');
    currentTask.textContent = 'Set reminder';
    currentStep.textContent = 'Scheduling alert';
    taskTitle.textContent = 'Create reminder';
    wakeWordState.textContent = 'Active';
    return;
  }

  setState('processing');
  currentTask.textContent = 'Understood';
  currentStep.textContent = 'Planning action';
  taskTitle.textContent = 'General assistant task';
  wakeWordState.textContent = 'Active';
}

document.getElementById('speakBtn').addEventListener('click', () => {
  listening = !listening;
  const state = listening ? 'listening' : 'ready';
  setState(state);
  commandText.textContent = listening
    ? '"Hey Nova, open Chrome and search Bihar Polytechnic syllabus."'
    : '"Voice listening paused."';
  wakeWordState.textContent = listening ? 'Ready' : 'Paused';
});

document.getElementById('stopBtn').addEventListener('click', () => {
  setState('paused');
  commandText.textContent = '"Stopping the current task."';
  wakeWordState.textContent = 'Standby';
});

runCommandBtn.addEventListener('click', () => {
  processCommand(commandInput.value);
});

commandInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    processCommand(commandInput.value);
  }
});

document.querySelectorAll('.action-btn').forEach((button) => {
  button.addEventListener('click', () => {
    if (button.id === 'contactsButton') return;
    const label = button.textContent.trim();
    commandText.textContent = `"${label} panel opened."`;
    setState('processing');
    currentTask.textContent = label;
    currentStep.textContent = 'Opening panel';
    taskTitle.textContent = `${label} panel`;
  });
});

setInterval(updateMetrics, 2000);
setState('ready');
