// kalmido-suite: fresh
// 2.1385.0 B2 (#6435 12): the placeholders and mentions of finished HTML are replaced only in the text, never inside a tag
// (an attribute) - own container (start.sh), jsdom, invented texts only:
// - htmlTextSub (icons.js): a match between tags is replaced, the same text inside an attribute stays; a placeholder with its
//   <p> wrapper is replaced whole
// - a knowledge page whose link path carries the text of a placeholder (the ```pages block's marker): the link keeps its
//   data-path, no markup lands in an attribute (before: the block's HTML was put into the link's data-path)
// - an inline formula's marker in a link path: no markup in an attribute; a real formula and a real ```pages block draw as before
// - a comment: <@id> in the text becomes the mention button, a link stays; no attribute carries the button's markup
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } return c; };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21385B2_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = async (fn, n = 60) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(150); } return fn(); };
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  await call(CK, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call(CK, 'GET', '/api/state'), me = st0.me.id;
  const feats = [...new Set([...(st0.settings.features || '').split(',').filter(Boolean), 'wiki', 'files', 'collab'])].join(',');
  await call(CK, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: feats});

  const w = await boot({user: 'alice', hash: 'wiki'});
  check(!!(await until(() => w.eval("typeof wk_render === 'function' && typeof wem_cut === 'function' && typeof htmlTextSub === 'function'"))), 'setup: the knowledge module is loaded');
  const R = js => w.eval(`(() => { ${js} })()`);

  // ---- the helper
  const u1 = R(`return htmlTextSub('<p>\\u2063X0\\u2063</p><a title="\\u2063X1\\u2063" href="#">t \\u2063X2\\u2063</a>', /(?:<p>)?\\u2063X(\\d+)\\u2063(?:<\\/p>)?/g, (_, n) => '[' + n + ']');`);
  check(u1 === '[0]<a title="⁣X1⁣" href="#">t [2]</a>', '#6435 12: htmlTextSub replaces in the text (with the <p> wrapper), not in the attribute: ' + u1);
  const u2 = R(`return htmlTextSub('a &lt;@5&gt; <a href="/x/&lt;@5&gt;">b</a>', /&lt;@(\\d+)&gt;/g, (m, id) => '<b>' + id + '</b>');`);
  check(u2 === 'a <b>5</b> <a href="/x/&lt;@5&gt;">b</a>', '#6435 12: a mention inside an attribute stays: ' + u2);

  // ---- a knowledge page: the marker of a ```pages block inside a link path
  const NA = "e => [...e.attributes].some(at => at.name !== 'class' && at.name !== 'data-mcard' && /<|wktoc|wkimath|mcard/.test(at.value))";  // markup in an attribute
  const page = R(`const x = document.createElement('div');
    x.innerHTML = wk_render({id: -77, space: 'private', body: 'See [[Folder/\\u2063WKT0\\u2063]] here.\\n\\n\`\`\`pages\\n\`\`\`\\n'});
    const a = x.querySelector('a.wklink');
    return {path: a ? a.getAttribute('data-path') : null, inattr: [...x.querySelectorAll('*')].some(${NA})};`);
  check(page.path === 'Folder/⁣WKT0⁣', '#6435 12: the link keeps its path (the marker stays text in the attribute): ' + JSON.stringify(page));
  check(!page.inattr, '#6435 12: no markup inside an attribute: ' + JSON.stringify(page));
  const toc = R(`const x = document.createElement('div'); x.innerHTML = wk_render({id: -78, space: 'private', body: 'Intro\\n\\n\`\`\`pages\\n\`\`\`\\n'}); return x.innerHTML;`);
  check(/wktoc/.test(toc) && !toc.includes('⁣'), '#6435 12: a real ```pages block is still drawn, no marker left: ' + toc.slice(0, 300));

  // ---- an inline formula's marker in a link path; a real formula still draws
  const im = R(`const x = document.createElement('div');
    x.innerHTML = wk_render({id: -79, space: 'private', body: 'Math \\\\(x^2\\\\) and [[Calc/\\u2063IM0\\u2063]]'});
    return {math: x.querySelectorAll('.wkimath').length, inattr: [...x.querySelectorAll('*')].some(${NA})};`);
  check(im.math >= 1 && !im.inattr, '#6435 12: the formula draws, no markup inside an attribute: ' + JSON.stringify(im));

  // ---- a comment: a mention in the text
  const cm = R(`const x = document.createElement('div');
    x.innerHTML = commentBody('Hi <@${me}> see [the file](https://example.com/a)', {${me}: 'Alice'});
    return {mentions: x.querySelectorAll('.mention').length, link: !!x.querySelector('a[href="https://example.com/a"]'), inattr: [...x.querySelectorAll('*')].some(${NA})};`);
  check(cm.mentions === 1 && cm.link && !cm.inattr, '#6435 12: the mention in the text is a button, the link stays, nothing inside an attribute: ' + JSON.stringify(cm));
  w.close();

  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
