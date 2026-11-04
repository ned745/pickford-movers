document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.textContent = open ? '×' : '☰';
    });
  }

  const launch = document.getElementById('assistantLaunch');
  const panel = document.getElementById('assistantPanel');
  const close = document.getElementById('assistantClose');
  if (launch && panel) {
    launch.addEventListener('click', () => { panel.hidden = !panel.hidden; });
  }
  if (close && panel) close.addEventListener('click', () => { panel.hidden = true; });
  const chatForm = document.getElementById('assistantForm');
  const chatInput = document.getElementById('assistantInput');
  const chatBox = document.getElementById('assistantChat');
  if (chatForm && chatInput && chatBox) {
    const addBubble = (message, who) => {
      const p = document.createElement('p');
      p.className = who === 'user' ? 'assistant-bubble assistant-user' : 'assistant-bubble';
      p.textContent = message;
      chatBox.appendChild(p);
      chatBox.scrollTop = chatBox.scrollHeight;
      return p;
    };
    chatForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const message = chatInput.value.trim();
      if (!message) return;
      addBubble(message, 'user');
      chatInput.value = '';
      const waiting = addBubble('One moment…', 'bot');
      const send = chatForm.querySelector('button');
      if (send) send.disabled = true;
      try {
        const response = await fetch('/assistant/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message})});
        const data = await response.json();
        waiting.textContent = data.reply || 'Sorry, I could not process that. Please contact our team.';
        if (data.action && data.action.url) {
          const link = document.createElement('a');
          link.className = 'quick-link'; link.href = data.action.url; link.textContent = data.action.label || 'Continue';
          if (data.action.url.startsWith('https://')) { link.target = '_blank'; link.rel = 'noopener'; }
          chatBox.appendChild(link);
        }
      } catch (error) {
        waiting.textContent = 'Connection issue. Please try again or contact us on WhatsApp.';
      } finally {
        if (send) send.disabled = false;
        chatBox.scrollTop = chatBox.scrollHeight;
      }
    });
  }

});
