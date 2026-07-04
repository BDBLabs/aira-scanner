export const config = {
  api: {
    bodyParser: true,
  },
};

import { runLLM } from '../lib/llm.js';

function buildPrompt(body) {
  if (typeof body?.prompt === 'string' && body.prompt.trim()) {
    return body.prompt.trim();
  }

  const firstMessage = Array.isArray(body?.messages) ? body.messages[0] : null;
  if (typeof firstMessage?.content === 'string' && firstMessage.content.trim()) {
    return firstMessage.content.trim();
  }

  return '';
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const system = typeof req.body?.system === 'string' ? req.body.system.trim() : '';
  const prompt = buildPrompt(req.body);
  const provider = typeof req.body?.provider === 'string' ? req.body.provider : 'auto';
  const model = typeof req.body?.model === 'string' ? req.body.model.trim() : '';
  const baseUrl = typeof req.body?.baseUrl === 'string' ? req.body.baseUrl.trim() : '';

  if (!prompt) {
    return res.status(400).json({ error: { message: 'No scan prompt provided.' } });
  }

  try {
    const result = await runLLM({ system, prompt, provider, model, baseUrl });

    return res.status(200).json({
      text: result.text,
      provider: result.provider,
      model: result.model
    });
  } catch (err) {
    return res.status(500).json({ error: { message: `Routing error: ${err.message}` } });
  }
}
