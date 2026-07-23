const stepsList = document.getElementById('stepsList');
const addStepBtn = document.getElementById('addStepBtn');
const loadSamplesBtn = document.getElementById('loadSamplesBtn');
const projectState = document.getElementById('projectState');
const stepTemplate = document.getElementById('stepTemplate');

const state = {
  steps: [],
};

function createId(prefix = 'step') {
  if (window.crypto?.randomUUID) {
    return `${prefix}-${window.crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getStepText(step) {
  return step.editor.textContent.replace(/\u00A0/g, ' ').trim();
}

function getContextForStep(stepIndex) {
  return state.steps
    .slice(0, stepIndex)
    .map((item) => getStepText(item))
    .filter(Boolean);
}

function setProjectState(message) {
  projectState.textContent = message;
}

function updateBadge(step, result) {
  step.card.classList.remove('step-card--correct', 'step-card--incorrect', 'step-card--uncertain');
  step.badge.classList.remove('step-badge--correct', 'step-badge--incorrect', 'step-badge--uncertain');

  if (result.status === 'correct') {
    step.card.classList.add('step-card--correct');
    step.badge.classList.add('step-badge--correct');
    step.badge.textContent = `Correct · ${Math.round(result.confidence * 100)}%`;
  } else if (result.status === 'incorrect') {
    step.card.classList.add('step-card--incorrect');
    step.badge.classList.add('step-badge--incorrect');
    step.badge.textContent = `Wrong · ${Math.round(result.confidence * 100)}%`;
  } else {
    step.card.classList.add('step-card--uncertain');
    step.badge.classList.add('step-badge--uncertain');
    step.badge.textContent = `Uncertain · ${Math.round(result.confidence * 100)}%`;
  }
}

function updateAnnotation(step, result) {
  const label = result.status === 'correct' ? 'Verified' : result.status === 'incorrect' ? 'Problem' : 'Uncertain';
  step.annotation.innerHTML = `<strong>${label}:</strong> ${result.short}<br /><span class="step-annotation--muted">${result.details}</span>`;
  step.confidence.textContent = `Confidence ${Math.round(result.confidence * 100)}%`;
}

function markEditing(step) {
  step.badge.textContent = 'Editing';
  step.card.classList.remove('step-card--correct', 'step-card--incorrect', 'step-card--uncertain');
  step.badge.classList.remove('step-badge--correct', 'step-badge--incorrect', 'step-badge--uncertain');
  step.annotation.innerHTML = '<span class="step-annotation--muted">Press Enter to check this step.</span>';
  step.confidence.textContent = 'Waiting for submission';
}

function mockVerifier(step, context) {
  const content = getStepText(step);
  const lastLine = context.at(-1) ?? '';

  if (!content) {
    return {
      step_id: step.id,
      status: 'uncertain',
      confidence: 0.2,
      short: 'No math step found',
      details: 'Write a line of math before checking the step.',
      fix: null,
      source: 'mock',
    };
  }

  const hasEquation = content.includes('=');
  const hasMathSymbols = /[+\-*/^]/.test(content);

  if (hasEquation || hasMathSymbols) {
    const sameAsReference = content.replace(/\s+/g, '') === lastLine.replace(/\s+/g, '');

    if (sameAsReference) {
      return {
        step_id: step.id,
        status: 'correct',
        confidence: 1,
        short: 'Step matches the previous line',
        details: 'The mock verifier treated this line as consistent with the reference line.',
        fix: null,
        source: 'mock',
      };
    }

    return {
      step_id: step.id,
      status: 'incorrect',
      confidence: 0.9,
      short: 'This line differs from the reference',
      details: 'The mock verifier detected a mismatch between the current line and the previous line.',
      fix: lastLine || 'Check the prior step',
      source: 'mock',
    };
  }

  return {
    step_id: step.id,
    status: 'uncertain',
    confidence: 0.5,
    short: 'Needs a clearer equation',
    details: 'The mock verifier could not confidently check this line yet.',
    fix: 'Write the step as an equation, such as x + 3 = 7.',
    source: 'mock',
  };
}

async function verifyStep(step) {
  const content = getStepText(step);
  const stepIndex = state.steps.indexOf(step);
  const context = getContextForStep(stepIndex);

  if (!content) {
    step.annotation.innerHTML = '<span class="step-annotation--muted">Write a math line before checking.</span>';
    return;
  }

  step.badge.textContent = 'Checking';
  step.annotation.innerHTML = '<span class="step-annotation--muted">Mock verifier is checking this line...</span>';
  setProjectState('Checking current step');

  const result = await new Promise((resolve) => {
    window.setTimeout(() => resolve(mockVerifier(step, context)), 220);
  });

  updateBadge(step, result);
  updateAnnotation(step, result);
  setProjectState('Editor shell active');
}

function createStep(initialText = '', focus = false) {
  const stepId = createId('step');
  const fragment = stepTemplate.content.cloneNode(true);
  const card = fragment.querySelector('.step-card');
  const number = fragment.querySelector('.step-number');
  const editor = fragment.querySelector('.step-editor');
  const badge = fragment.querySelector('.step-badge');
  const annotation = fragment.querySelector('.step-annotation');
  const source = fragment.querySelector('.step-card__source');
  const confidence = fragment.querySelector('.step-card__confidence');

  number.textContent = `${state.steps.length + 1}.`;
  editor.textContent = initialText;
  source.textContent = 'Mock verifier';
  confidence.textContent = 'Waiting for submission';
  card.dataset.stepId = stepId;

  const step = {
    id: stepId,
    card,
    editor,
    badge,
    annotation,
    confidence,
    number,
    checkToken: 0,
  };

  editor.addEventListener('input', () => {
    number.textContent = `${state.steps.indexOf(step) + 1}.`;
    markEditing(step);
  });

  editor.addEventListener('keydown', async (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      await verifyStep(step);
      createStep('', true);
    }
  });

  editor.addEventListener('paste', (event) => {
    event.preventDefault();
    const pastedText = event.clipboardData?.getData('text/plain') ?? '';
    document.execCommand('insertText', false, pastedText);
  });

  state.steps.push(step);
  stepsList.append(fragment);

  if (focus) {
    window.requestAnimationFrame(() => editor.focus());
  }

  if (!initialText) {
    markEditing(step);
  }

  return step;
}

function loadSamples() {
  stepsList.innerHTML = '';
  state.steps.length = 0;

  [
    'x + 3 = 7',
    '2*x + 6 = 14',
    '2*x + 5 = 14',
  ].forEach((line, index) => {
    const step = createStep(line, false);
    const startingState =
      index === 0
        ? { status: 'uncertain', confidence: 0.5, short: 'Sample reference line', details: 'Use this as the prior step for testing.' }
        : index === 1
          ? { status: 'correct', confidence: 1, short: 'Sample correct line', details: 'This line is set up to read as a good step in the mock flow.' }
          : { status: 'incorrect', confidence: 0.9, short: 'Sample incorrect line', details: 'This line is set up to read as a mismatch in the mock flow.' };

    updateBadge(step, startingState);
    updateAnnotation(step, startingState);
  });

  setProjectState('Samples loaded');
  state.steps.at(-1)?.editor.focus();
}

addStepBtn.addEventListener('click', () => createStep('', true));
loadSamplesBtn.addEventListener('click', () => loadSamples());

createStep('', true);
setProjectState('Editor shell active');
