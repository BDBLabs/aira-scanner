import assert from 'node:assert/strict';
import test from 'node:test';

import { runLLM } from '../lib/llm.js';


const PROVIDER_ENV = [
  'AIRA_NVIDIA_API_KEY', 'NVIDIA_API_KEY',
  'AIRA_GROQ_API_KEY', 'GROQ_API_KEY',
  'AIRA_GEMINI_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY',
  'AIRA_OPENROUTER_API_KEY', 'OPENROUTER_API_KEY',
  'AIRA_OLLAMA_MODEL', 'OLLAMA_MODEL'
];


function withEnvironment(values, callback) {
  const previous = Object.fromEntries(PROVIDER_ENV.map(key => [key, process.env[key]]));
  PROVIDER_ENV.forEach(key => delete process.env[key]);
  Object.assign(process.env, values);
  return Promise.resolve()
    .then(callback)
    .finally(() => {
      PROVIDER_ENV.forEach(key => delete process.env[key]);
      Object.entries(previous).forEach(([key, value]) => {
        if (value !== undefined) process.env[key] = value;
      });
    });
}


const cases = [
  ['nvidia', { NVIDIA_API_KEY: 'test-key' }],
  ['groq', { GROQ_API_KEY: 'test-key' }],
  ['openrouter', { OPENROUTER_API_KEY: 'test-key' }],
  ['gemini', { GEMINI_API_KEY: 'test-key' }]
];


for (const [provider, env] of cases) {
  test(`${provider} honors an explicit model override`, async () => {
    const requests = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
      requests.push({ url: String(url), body: JSON.parse(options.body) });
      const payload = provider === 'gemini'
        ? { candidates: [{ content: { parts: [{ text: '{"ok":true}' }] } }] }
        : { choices: [{ message: { content: '{"ok":true}' } }] };
      return { ok: true, json: async () => payload };
    };
    try {
      await withEnvironment(env, async () => {
        const result = await runLLM({
          provider,
          model: 'explicit-model-id',
          prompt: 'Return JSON.'
        });
        assert.equal(result.model, 'explicit-model-id');
      });
    } finally {
      globalThis.fetch = originalFetch;
    }

    assert.equal(requests.length, 1);
    if (provider === 'gemini') {
      assert.match(requests[0].url, /explicit-model-id/);
    } else {
      assert.equal(requests[0].body.model, 'explicit-model-id');
    }
  });
}
