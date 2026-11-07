import { cp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// HTML remains the source of truth. Generated copies are ignored by Git.
const web = fileURLToPath(new URL('../', import.meta.url));
const source = path.resolve(web, '../HTML');
const destination = path.resolve(web, 'public/workspace');
await mkdir(destination, { recursive: true });
const navigation = `<nav aria-label="账清项目入口" style="position:relative;z-index:100;display:flex;flex-wrap:wrap;gap:16px;padding:9px 10%;background:#e6f8fb;color:#243e4c;font:12px/1.6 system-ui"><strong>历史演示</strong><a href="/">品牌首页</a><a href="/upload/">客户提交</a><a href="/owner/">真实老板端</a><a href="/demo/">客户演示</a></nav>`;
for (const entry of await readdir(source, { withFileTypes: true })) {
  if (!entry.isFile() || !entry.name.endsWith('.html')) continue;
  const markup = await readFile(path.join(source, entry.name), 'utf8');
  await writeFile(path.join(destination, entry.name), markup.replace(/<body\b[^>]*>/i, '$&' + navigation), 'utf8');
}
for (const directory of ['css', 'js']) {
  await cp(path.join(source, directory), path.join(destination, directory), { recursive: true });
}
console.log('Prepared legacy HTML pages at /workspace/index.html');
