import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

// Use the existing compiler to exercise the production TS/TSX without a new test framework.
async function loadTypeScript(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
  return import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`);
}
const { toBubbles } = await loadTypeScript('../components/chat/history.ts');

const componentPath = fileURLToPath(new URL('../components/chat/ChatMessages.tsx', import.meta.url));
const compiled = ts.transpileModule(readFileSync(componentPath, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
});
const component = { exports: {} };
new vm.Script(compiled.outputText, { filename: componentPath }).runInNewContext({
  module: component, exports: component.exports, require: createRequire(componentPath),
});
const { ChatMessages } = component.exports;

test('parsed history preserves literal escapes, actual controls and whitespace', () => {
  const text = '  To: alice@example.test\r\nSubject: Exact review\n\nLiteral \\n \\t \\r \\\\; actual\tcontrol\r\n旅🦉  ';
  const payload = JSON.parse(JSON.stringify({ messages: [{ role: 'assistant', content: text }] }));
  const messages = toBubbles(payload);
  assert.equal(messages[0].text, text);
  assert.equal(messages[0].role, 'assistant');
});

test('a large reviewed body survives JSON, history conversion and the actual chat component', () => {
  const text = 'To: alice@example.test\nSubject: Reviewed draft\n\nStart \\n stays literal\r\n'
    + '旅🦉'.repeat(20000) + '\nMIDDLE <script>literal text</script> & \\t\n'
    + 'é'.repeat(90000) + '\nEND  ';
  const messages = toBubbles(JSON.parse(JSON.stringify({ messages: [{ role: 'assistant', content: text }] })));
  const markup = renderToStaticMarkup(React.createElement(ChatMessages, {
    messages, isWaitingForResponse: false, scrollContainerRef: { current: null }, onScroll() {},
  }));
  const completeTextSpan = renderToStaticMarkup(React.createElement('span', { className: 'whitespace-pre-wrap' }, text));
  assert.ok(Buffer.byteLength(text) > 300000);
  assert.ok(markup.includes(completeTextSpan), 'The complete reviewed text must be rendered without rewriting or truncation');
  assert.ok(!markup.includes('<script>literal text</script>'));
});

test('invalid or empty history entries are ignored without altering valid entries', () => {
  for (const payload of [null, undefined, 42, {}, { messages: 'not a list' }, { messages: [] }]) {
    assert.deepEqual(toBubbles(payload), []);
  }
  assert.deepEqual(toBubbles({ messages: [null, {}, { role: 'user', content: 42 },
    { role: 'assistant', content: ' \n\t ' }, { role: 'user', content: '  exact  ' }] }),
  [{ id: 'history-0', role: 'user', text: '  exact  ' }]);
});

test('the chat proxy preserves content and asynchronous acceptance', async () => {
  const originalFetch = globalThis.fetch;
  const originalServer = process.env.PY_SERVER_URL;
  const originalPath = process.env.PY_CHAT_PATH;
  const calls = [];
  try {
    process.env.PY_SERVER_URL = 'http://release-backend.test';
    process.env.PY_CHAT_PATH = '/api/v1/chat/send';
    globalThis.fetch = async (url, options) => {
      calls.push({ url, ...options });
      return new Response('', { status: 202 });
    };
    const { POST } = await loadTypeScript('../app/api/chat/route.ts');
    const response = await POST(new Request('http://release-web.test/api/chat', { method: 'POST',
      body: JSON.stringify({ messages: [{ role: 'user', parts: [{ type: 'text', text: 'Keep \\n literal' },
        { type: 'text', text: '\r\n旅🦉' }] }] }), headers: { 'Content-Type': 'application/json' },
    }));
    assert.equal(response.status, 202);
    assert.equal(await response.text(), '');
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, 'http://release-backend.test/api/v1/chat/send');
    assert.equal(calls[0].method, 'POST');
    assert.deepEqual(JSON.parse(calls[0].body).messages, [{ role: 'user', content: 'Keep \\n literal\r\n旅🦉' }]);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalServer === undefined) delete process.env.PY_SERVER_URL;
    else process.env.PY_SERVER_URL = originalServer;
    if (originalPath === undefined) delete process.env.PY_CHAT_PATH;
    else process.env.PY_CHAT_PATH = originalPath;
  }
});

test('the history proxy returns the complete review and forwards clearing', async () => {
  const originalFetch = globalThis.fetch;
  const originalServer = process.env.PY_SERVER_URL;
  const review = 'To: alice@example.test\n\nLiteral \\n\r\n' + '旅🦉'.repeat(60000) + '\nEND  ';
  const payload = { messages: [{ role: 'assistant', content: review }] };
  const calls = [];
  try {
    process.env.PY_SERVER_URL = 'http://release-backend.test/';
    globalThis.fetch = async (url, options) => {
      calls.push({ url, ...options });
      return new Response(JSON.stringify(options.method === 'DELETE' ? { ok: true } : payload), { status: 200 });
    };
    const { GET, DELETE } = await loadTypeScript('../app/api/chat/history/route.ts');
    const history = await GET();
    assert.equal(history.status, 200);
    assert.equal(toBubbles(await history.json())[0].text, review);
    const cleared = await DELETE();
    assert.equal(cleared.status, 200);
    assert.deepEqual(await cleared.json(), { ok: true });
    assert.deepEqual(calls.map(call => call.method), ['GET', 'DELETE']);
    assert.ok(calls.every(call => call.url === 'http://release-backend.test/api/v1/chat/history'));
  } finally {
    globalThis.fetch = originalFetch;
    if (originalServer === undefined) delete process.env.PY_SERVER_URL;
    else process.env.PY_SERVER_URL = originalServer;
  }
});
