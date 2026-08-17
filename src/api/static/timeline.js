// Chevron-strip timeline: fetches GET /timeline and renders one
// horizontally-scrollable arrow row per era, illustrations alternating
// above/below the arrow. Self-contained: wires up the "Show Timeline"
// button itself, reusing the same #ask-form / #question / #result elements
// index.html's own script uses for /ask.
(function () {
  const timelineBtn = document.getElementById('timeline-btn');
  const resultDiv = document.getElementById('result');
  const form = document.getElementById('ask-form');
  const input = document.getElementById('question');
  if (!timelineBtn || !resultDiv || !form || !input) return;

  const ERA_COLOR_COUNT = 5;

  const preview = document.createElement('div');
  preview.className = 'tl-preview';
  preview.hidden = true;
  preview.innerHTML = '<img alt=""><span></span>';
  document.body.appendChild(preview);
  const previewImg = preview.querySelector('img');
  const previewLabel = preview.querySelector('span');

  function showPreview(node, illustration) {
    if (!illustration) return;
    previewImg.src = illustration.url;
    previewImg.alt = node.dataset.eventId;
    previewLabel.textContent = node.dataset.eventId;
    preview.hidden = false;

    const rect = node.getBoundingClientRect();
    const previewWidth = preview.offsetWidth || 200;
    let left = rect.left + rect.width / 2 - previewWidth / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - previewWidth - 8));
    let top = rect.top - preview.offsetHeight - 12;
    if (top < 8) top = rect.bottom + 12;
    preview.style.left = `${left}px`;
    preview.style.top = `${top}px`;
  }

  function hidePreview() {
    preview.hidden = true;
  }

  function buildNode(event, index, eraIndex) {
    const node = document.createElement('div');
    node.className = 'tl-node';
    node.dataset.eventId = event.id;
    node.tabIndex = 0;
    node.setAttribute('role', 'button');
    node.style.setProperty('--tl-color', `var(--tl-era-${eraIndex % ERA_COLOR_COUNT})`);

    const topSlot = document.createElement('div');
    topSlot.className = 'tl-slot tl-slot-top';
    const bottomSlot = document.createElement('div');
    bottomSlot.className = 'tl-slot tl-slot-bottom';

    const label = document.createElement('div');
    label.className = 'tl-label';
    label.textContent = event.id;
    const portrait = document.createElement('div');
    portrait.className = 'tl-portrait' + (event.illustration ? '' : ' tl-placeholder');
    if (event.illustration) {
      const img = document.createElement('img');
      img.src = event.illustration.url;
      img.alt = event.id;
      portrait.appendChild(img);
      portrait.addEventListener('mouseenter', () => showPreview(node, event.illustration));
      portrait.addEventListener('mouseleave', hidePreview);
    }
    const connector = document.createElement('div');
    connector.className = 'tl-connector';

    const above = index % 2 === 0;
    const slot = above ? topSlot : bottomSlot;
    if (above) {
      slot.append(label, portrait, connector);
    } else {
      slot.append(connector, portrait, label);
    }

    const chevron = document.createElement('div');
    chevron.className = 'tl-chevron';

    node.append(topSlot, chevron, bottomSlot);

    node.addEventListener('click', () => askAbout(event.id));
    node.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      askAbout(event.id);
    });

    return node;
  }

  function askAbout(eventId) {
    input.value = `Explain ${eventId} event`;
    form.requestSubmit();
  }

  function renderTimeline(data) {
    const wrap = document.createElement('div');
    wrap.className = 'card tl-timeline';

    data.eras.forEach((era, eraIndex) => {
      const section = document.createElement('div');
      section.className = 'tl-era';

      const title = document.createElement('div');
      title.className = 'tl-era-title';
      title.textContent = era.era;

      const strip = document.createElement('div');
      strip.className = 'tl-strip';
      era.events.forEach((event, i) => strip.appendChild(buildNode(event, i, eraIndex)));

      section.append(title, strip);
      wrap.appendChild(section);
    });

    resultDiv.innerHTML = '';
    resultDiv.appendChild(wrap);
  }

  timelineBtn.addEventListener('click', async () => {
    timelineBtn.disabled = true;
    resultDiv.innerHTML = '<div class="card">Loading timeline…</div>';
    hidePreview();

    try {
      const res = await fetch('/timeline');
      const data = await res.json();

      if (!res.ok) {
        resultDiv.innerHTML = `<div class="card error">${data.detail || 'Something went wrong.'}</div>`;
        return;
      }
      renderTimeline(data);
    } catch (err) {
      resultDiv.innerHTML = '<div class="card error">Network error — please try again.</div>';
    } finally {
      timelineBtn.disabled = false;
    }
  });
})();
