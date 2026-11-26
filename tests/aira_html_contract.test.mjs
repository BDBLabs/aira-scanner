import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import scanHandler from '../api/scan.js';


const ENV_KEYS = [
  'AIRA_NVIDIA_API_KEY', 'NVIDIA_API_KEY',
  'AIRA_GROQ_API_KEY', 'GROQ_API_KEY', 'GROQ_MODEL', 'AIRA_GROQ_MODEL',
  'AIRA_GEMINI_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY',
  'AIRA_OPENROUTER_API_KEY', 'OPENROUTER_API_KEY', 'OPENROUTER_MODEL', 'AIRA_OPENROUTER_MODEL',
  'AIRA_OLLAMA_MODEL', 'OLLAMA_MODEL', 'AIRA_OLLAMA_HOST', 'OLLAMA_HOST',
  'AIRA_NVIDIA_MODEL', 'NVIDIA_MODEL', 'AIRA_GEMINI_MODEL', 'GEMINI_MODEL'
];


function withEnvironment(values, callback) {
  const previous = Object.fromEntries(ENV_KEYS.map(key => [key, process.env[key]]));
  ENV_KEYS.forEach(key => delete process.env[key]);
  Object.assign(process.env, values);
  return Promise.resolve()
    .then(callback)
    .finally(() => {
      ENV_KEYS.forEach(key => delete process.env[key]);
      Object.entries(previous).forEach(([key, value]) => {
        if (value !== undefined) process.env[key] = value;
      });
    });
}


function fakeResponse() {
  const result = { statusCode: null, headers: {}, body: undefined };
  const res = {
    setHeader(name, value) {
      result.headers[name.toLowerCase()] = value;
      return res;
    },
    status(code) {
      result.statusCode = code;
      return res;
    },
    json(payload) {
      result.body = payload;
      return res;
    },
    end() {
      return res;
    }
  };
  return { res, result };
}


test('aira.html has no browser-side credentials or direct Anthropic call', () => {
  const html = readFileSync(new URL('../aira.html', import.meta.url), 'utf8');

  assert.doesNotMatch(html, /api\.anthropic\.com/i);
  assert.doesNotMatch(html, /claude-sonnet/i);
  assert.doesNotMatch(html, /api\.airtable\.com/i);
  assert.doesNotMatch(html, /AIRTABLE_TOKEN|YOUR_AIRTABLE_PAT|YOUR_BASE_ID/i);
  assert.doesNotMatch(html, /Authorization:\s*`Bearer/i);
  assert.doesNotMatch(html, /baseUrl/i);
  assert.doesNotMatch(html, /code\.slice\(0,\s*8000\)/);

  assert.match(html, /MAX_SCAN_CHARS\s*=\s*8000/);
  assert.match(html, /fetch\('\/api\/health'/);
  assert.match(html, /fetch\('\/api\/scan'/);
  assert.match(html, /fetch\('\/api\/research'/);
  assert.match(html, /Partial scan:/);
  assert.match(html, /no API key was sent by the browser/i);
});


test('/api/scan reports an explicit unconfigured state without credentials', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error('network disabled in test');
  };

  try {
    await withEnvironment({}, async () => {
      const { res, result } = fakeResponse();
      await scanHandler(
        { method: 'POST', body: { provider: 'auto', system: '', prompt: 'Return JSON.' } },
        res
      );

      assert.equal(result.statusCode, 500);
      assert.match(result.body.error.message, /No providers are configured/);
      assert.doesNotMatch(JSON.stringify(result.body), /dummy|sk-/i);
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test('/api/scan reads the provider key from server env and does not echo it', async () => {
  const requests = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    requests.push({
      url: String(url),
      headers: options.headers,
      body: JSON.parse(options.body)
    });
    return {
      ok: true,
      json: async () => ({ choices: [{ message: { content: '{"ok":true}' } }] })
    };
  };

  try {
    await withEnvironment({ GROQ_API_KEY: 'dummy-server-key' }, async () => {
      const { res, result } = fakeResponse();
      await scanHandler(
        { method: 'POST', body: { provider: 'groq', system: 'system', prompt: 'prompt' } },
        res
      );

      assert.equal(result.statusCode, 200);
      assert.equal(result.body.text, '{"ok":true}');
      assert.equal(result.body.provider, 'groq');
      assert.doesNotMatch(JSON.stringify(result.body), /dummy-server-key/);
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requests.length, 1);
  assert.match(requests[0].url, /api\.groq\.com/);
  assert.equal(requests[0].headers.Authorization, 'Bearer dummy-server-key');
  assert.equal(requests[0].body.messages.at(-1).content, 'prompt');
});
