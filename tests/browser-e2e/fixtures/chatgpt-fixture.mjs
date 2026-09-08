const SENSITIVE_MARKER = 'SENSITIVE_FIXTURE_TEXT_DO_NOT_PERSIST';

function composerMarkup(shape) {
  if (shape === 'plaintext') {
    return '<div id="prompt-textarea" role="textbox" contenteditable="plaintext-only"></div>';
  }
  if (shape === 'contenteditable') {
    return '<div id="prompt-textarea" role="textbox" contenteditable="true"></div>';
  }
  if (shape === 'textarea') {
    return '<textarea id="prompt-textarea" role="textbox"></textarea>';
  }
  if (shape === 'wrapper') {
    return '<div id="prompt-textarea" role="textbox" contenteditable="false"><div role="textbox" contenteditable="plaintext-only"></div></div>';
  }
  if (shape === 'nonempty') {
    return '<div id="prompt-textarea" role="textbox" contenteditable="plaintext-only">Existing unsent text</div>';
  }
  if (shape === 'unsupported') {
    return '<div id="prompt-textarea" role="textbox" contenteditable="false"><span>Unsupported editor shell</span></div>';
  }
  if (shape === 'missing') return '<div id="no-composer"></div>';
  return '<div id="prompt-textarea" role="textbox" contenteditable="plaintext-only"></div>';
}

export function fixtureHtml(urlString) {
  const url = new URL(urlString);
  const shape = url.searchParams.get('shape') ?? 'plaintext';
  return `<!doctype html>
<html><head><meta charset="utf-8"><title>MetaChat synthetic ChatGPT fixture</title></head>
<body>
<form id="fixture-form">${composerMarkup(shape)}</form>
<script>
(() => {
  const counts = { inputCount: 0, keydownCount: 0, keyupCount: 0, clickCount: 0, submitCount: 0 };
  window.__metachatCounts = counts;
  document.addEventListener('input', () => counts.inputCount++, true);
  document.addEventListener('keydown', () => counts.keydownCount++, true);
  document.addEventListener('keyup', () => counts.keyupCount++, true);
  document.addEventListener('click', () => counts.clickCount++, true);
  document.addEventListener('submit', (event) => { counts.submitCount++; event.preventDefault(); }, true);
  let firstError = null;
  window.__emitStreamError = () => {
    if (!firstError) {
      firstError = document.createElement('div');
      firstError.setAttribute('role', 'alert');
      firstError.dataset.fixtureSecret = ${JSON.stringify(SENSITIVE_MARKER)};
      firstError.textContent = 'Error in message stream';
      document.body.append(firstError);
    }
    firstError.setAttribute('class', 'error error-repeated');
    firstError.firstChild && (firstError.firstChild.textContent = 'Error in message stream');
    firstError.setAttribute('aria-hidden', 'false');
    return true;
  };
  window.__emitSecondStreamError = () => {
    const node = document.createElement('div');
    node.setAttribute('role', 'alert');
    node.dataset.fixtureSecret = ${JSON.stringify(SENSITIVE_MARKER)};
    node.textContent = 'Error in message stream';
    document.body.append(node);
    return true;
  };
})();
</script>
</body></html>`;
}

// Contract markers kept in source for auditability:
// contenteditable="plaintext-only"
// contenteditable="true"
// textarea
// prompt-textarea
// inputCount keydownCount keyupCount clickCount submitCount
