import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const python=process.env.E2E_PYTHON || (process.platform==='win32'?'../server/.venv/Scripts/python.exe':'../server/.venv/bin/python');
const child=spawn(python,['-X','utf8',fileURLToPath(new URL('../../server/tests/browser_stack.py',import.meta.url))],{stdio:'inherit',windowsHide:true});
process.on('SIGTERM',()=>child.kill());process.on('SIGINT',()=>child.kill());child.on('exit',code=>process.exit(code||0));
