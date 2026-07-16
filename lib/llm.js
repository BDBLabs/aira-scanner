const AUTO_PROVIDER_ORDER = ['ollama', 'nvidia', 'groq', 'gemini', 'openrouter'];
const MAX_ATTEMPTS_PER_PROVIDER = 2;
const OLLAMA_DISCOVERY_TIMEOUT_MS = 5000;
const NVIDIA_BASE_URL = 'https://integrate.api.nvidia.com/v1';

function configuredModel(provider, overrides = {}) {
  if (typeof overrides.model === 'string' && overrides.model.trim() && overrides.model !== 'auto') {
    return overrides.model.trim();
  }
  if (provider === 'ollama') return process.env.AIRA_OLLAMA_MODEL || process.env.OLLAMA_MODEL || null;
  if (provider === 'nvidia') return process.env.AIRA_NVIDIA_MODEL || process.env.NVIDIA_MODEL || 'stepfun-ai/step-3.7-flash';
  if (provider === 'groq') return process.env.AIRA_GROQ_MODEL || process.env.GROQ_MODEL || 'llama-3.1-8b-instant';
  if (provider === 'gemini') return process.env.AIRA_GEMINI_MODEL || process.env.GEMINI_MODEL || 'gemini-2.5-flash';
  if (provider === 'openrouter') return process.env.AIRA_OPENROUTER_MODEL || process.env.OPENROUTER_MODEL || null;
  return null;
}

function providerBaseUrl(provider, overrides = {}) {
  if (typeof overrides.baseUrl === 'string' && overrides.baseUrl.trim()) {
    return overrides.baseUrl.trim().replace(/\/$/, '');
  }
  if (provider === 'ollama') {
    return (process.env.AIRA_OLLAMA_HOST || process.env.OLLAMA_HOST || 'http://127.0.0.1:11434').replace(/\/$/, '');
  }
  if (provider === 'nvidia') {
    return NVIDIA_BASE_URL;
  }
  return null;
}

function providerApiKey(provider) {
  if (provider === 'nvidia') return process.env.AIRA_NVIDIA_API_KEY || process.env.NVIDIA_API_KEY || null;
  if (provider === 'groq') return process.env.AIRA_GROQ_API_KEY || process.env.GROQ_API_KEY || null;
  if (provider === 'openrouter') return process.env.AIRA_OPENROUTER_API_KEY || process.env.OPENROUTER_API_KEY || null;
  if (provider === 'gemini') return process.env.AIRA_GEMINI_API_KEY || process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || null;
  return null;
}

async function parseJsonResponse(response, providerName) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message =
      data?.error?.message ||
      data?.error?.metadata?.raw ||
      data?.message ||
      `${providerName} API error ${response.status}`;
    throw new Error(message);
  }
  return data;
}

async function fetchOllamaModels(baseUrl) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), OLLAMA_DISCOVERY_TIMEOUT_MS);
  try {
    const response = await fetch(`${baseUrl}/api/tags`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal
    });
    const data = await parseJsonResponse(response, 'Ollama');
    return Array.isArray(data?.models)
      ? data.models
          .map(model => typeof model?.name === 'string' ? model.name.trim() : '')
          .filter(Boolean)
      : [];
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error('Ollama discovery timed out');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function ollamaSnapshot(overrides = {}) {
  const baseUrl = providerBaseUrl('ollama', overrides);
  const model = configuredModel('ollama', overrides);
  const snapshot = {
    configured: Boolean(model),
    model,
    base_url: baseUrl,
    reachable: false,
    available_models: [],
    selected_model_available: null
  };

  try {
    const models = await fetchOllamaModels(baseUrl);
    snapshot.reachable = true;
    snapshot.available_models = models;
    if (model) {
      snapshot.selected_model_available = models.includes(model);
    }
  } catch (error) {
    snapshot.message = `Ollama discovery failed: ${error.message}`;
  }

  return snapshot;
}

async function configuredProviders(overrides = {}) {
  const providers = [];
  const ollama = await ollamaSnapshot(overrides);
  if (ollama.configured) providers.push('ollama');
  if (providerApiKey('nvidia')) providers.push('nvidia');
  if (providerApiKey('groq')) providers.push('groq');
  if (providerApiKey('gemini')) providers.push('gemini');
  if (providerApiKey('openrouter') && configuredModel('openrouter', overrides)) providers.push('openrouter');
  return { providers, ollama };
}

function buildMessages(system, prompt) {
  return [
    system ? { role: 'system', content: system } : null,
    { role: 'user', content: prompt }
  ].filter(Boolean);
}

function parseOpenAiCompatibleText(data) {
  const content = data?.choices?.[0]?.message?.content;
  if (typeof content === 'string') return content.trim();
  if (Array.isArray(content)) {
    return content
      .map(part => typeof part?.text === 'string' ? part.text : '')
      .join('')
      .trim();
  }
  return '';
}

function ensureValidJson(text) {
  const cleaned = text.replace(/```json|```/g, '').trim();
  JSON.parse(cleaned);
  return cleaned;
}

async function callNvidia({ system, prompt }) {
  const apiKey = providerApiKey('nvidia');
  if (!apiKey) {
    throw new Error('NVIDIA_API_KEY is not configured.');
  }

  const model = configuredModel('nvidia');
  const response = await fetch(`${NVIDIA_BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: buildMessages(system, prompt)
    })
  });

  const data = await parseJsonResponse(response, 'NVIDIA');
  return {
    provider: 'nvidia',
    model,
    text: ensureValidJson(parseOpenAiCompatibleText(data))
  };
}

async function callGroq({ system, prompt }) {
  const apiKey = providerApiKey('groq');
  if (!apiKey) {
    throw new Error('GROQ_API_KEY is not configured.');
  }

  const model = configuredModel('groq');
  const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: buildMessages(system, prompt)
    })
  });

  const data = await parseJsonResponse(response, 'Groq');
  return {
    provider: 'groq',
    model,
    text: ensureValidJson(parseOpenAiCompatibleText(data))
  };
}

async function callOpenRouter({ system, prompt }) {
  const apiKey = providerApiKey('openrouter');
  const model = configuredModel('openrouter');
  if (!apiKey || !model) {
    throw new Error('OPENROUTER_API_KEY and OPENROUTER_MODEL must both be configured.');
  }

  const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: buildMessages(system, prompt)
    })
  });

  const data = await parseJsonResponse(response, 'OpenRouter');
  return {
    provider: 'openrouter',
    model,
    text: ensureValidJson(parseOpenAiCompatibleText(data))
  };
}

async function callGemini({ system, prompt }) {
  const apiKey = providerApiKey('gemini');
  if (!apiKey) {
    throw new Error('GEMINI_API_KEY or GOOGLE_API_KEY is not configured.');
  }

  const model = configuredModel('gemini');
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(apiKey)}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        systemInstruction: system ? { parts: [{ text: system }] } : undefined,
        contents: [
          {
            role: 'user',
            parts: [{ text: prompt }]
          }
        ],
        generationConfig: {
          temperature: 0,
          responseMimeType: 'application/json'
        }
      })
    }
  );

  const data = await parseJsonResponse(response, 'Gemini');
  const text = (data?.candidates || [])
    .flatMap(candidate => candidate?.content?.parts || [])
    .map(part => part?.text || '')
    .join('')
    .trim();

  if (!text) {
    throw new Error('Gemini returned an empty response.');
  }

  return {
    provider: 'gemini',
    model,
    text: ensureValidJson(text)
  };
}

async function callOllama({ system, prompt, model, baseUrl }) {
  const resolvedBaseUrl = providerBaseUrl('ollama', { baseUrl });
  const resolvedModel = configuredModel('ollama', { model });
  if (!resolvedBaseUrl || !resolvedModel) {
    throw new Error('Ollama is not configured. Set AIRA_OLLAMA_MODEL or pass a model explicitly.');
  }

  const availableModels = await fetchOllamaModels(resolvedBaseUrl).catch(() => []);
  if (availableModels.length > 0 && !availableModels.includes(resolvedModel)) {
    const sample = availableModels.slice(0, 10).join(', ');
    const more = availableModels.length > 10 ? ' ...' : '';
    throw new Error(`Selected Ollama model '${resolvedModel}' is not available. Available models: ${sample}${more}`);
  }

  const response = await fetch(`${resolvedBaseUrl}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: resolvedModel,
      stream: false,
      format: 'json',
      messages: buildMessages(system, prompt),
      options: { temperature: 0 }
    })
  });

  const data = await parseJsonResponse(response, 'Ollama');
  const text = (data?.message?.content || '').trim();
  if (!text) {
    throw new Error('Ollama returned an empty response.');
  }

  return {
    provider: 'ollama',
    model: resolvedModel,
    text: ensureValidJson(text)
  };
}

const PROVIDERS = {
  ollama: callOllama,
  nvidia: callNvidia,
  groq: callGroq,
  openrouter: callOpenRouter,
  gemini: callGemini
};

export async function providerHealthSnapshot(overrides = {}) {
  const { providers, ollama } = await configuredProviders(overrides);
  return {
    ok: providers.length > 0,
    recommended_provider: providers[0] === 'ollama' ? 'ollama' : providers[0] === 'nvidia' ? 'nvidia' : 'groq',
    auto_provider_order: AUTO_PROVIDER_ORDER,
    configured_providers: providers,
    heuristic_fallback: true,
    providers: {
      ollama,
      nvidia: {
        configured: providers.includes('nvidia'),
        model: configuredModel('nvidia'),
        base_url: NVIDIA_BASE_URL
      },
      groq: {
        configured: providers.includes('groq'),
        model: configuredModel('groq')
      },
      gemini: {
        configured: providers.includes('gemini'),
        model: configuredModel('gemini')
      },
      openrouter: {
        configured: providers.includes('openrouter'),
        model: configuredModel('openrouter')
      }
    }
  };
}

export async function runLLM({ system = '', prompt = '', provider = 'auto', model = '', baseUrl = '' }) {
  if (!prompt.trim()) {
    throw new Error('No scan prompt provided.');
  }

  const { providers } = await configuredProviders({ model, baseUrl });
  const providerOrder = provider === 'auto'
    ? providers
    : [provider];

  if (providerOrder.length === 0) {
    throw new Error(
      'No providers are configured. Set AIRA_OLLAMA_MODEL or OLLAMA_MODEL for Ollama, or configure NVIDIA/Groq/Gemini/OpenRouter env vars.'
    );
  }

  const errors = [];
  for (const providerName of providerOrder) {
    const runner = PROVIDERS[providerName];
    if (!runner) {
      errors.push(`${providerName}: unsupported provider`);
      continue;
    }

    for (let attempt = 1; attempt <= MAX_ATTEMPTS_PER_PROVIDER; attempt += 1) {
      try {
        return await runner({ system, prompt, model, baseUrl });
      } catch (err) {
        errors.push(`${providerName} attempt ${attempt}: ${err.message}`);
      }
    }
  }

  throw new Error(`All configured providers failed. ${errors.join(' | ')}`);
}
