"""Run one explicitly listed review command and retain its exit status and log."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
EVAL = str(ROOT / 'evals/agent_overload/run.py')
RANKERS = ['heuristic_v1', 'idf_v1', 'bm25_v1']

def evaluation(name, *arguments):
    return [PYTHON, EVAL, *arguments, '--output', str(HERE / name)]

COMMANDS = {
    'backend': ([PYTHON, str(ROOT / 'server/tests/run_tests.py')], 300),
    'frontend': (['npm.cmd', '--prefix', str(ROOT / 'web'), 'test'], 180),
    'lint': (['npm.cmd', '--prefix', str(ROOT / 'web'), 'run', 'lint', '--', '--no-cache'], 180),
    'typecheck': ([str(ROOT / 'web/node_modules/.bin/tsc.cmd'), '--project', str(ROOT / 'web/tsconfig.json'), '--noEmit'], 180),
    'build': (['npm.cmd', '--prefix', str(ROOT / 'web'), 'run', 'build'], 300),
    'baseline': (evaluation('baseline'), 180),
    'scripted': (evaluation('scripted', '--compare', '--context-window', '65536'), 180),
    'ranking-v1': (evaluation('ranking-v1', '--compare-rankers', *RANKERS, '--sizes', '100', '1000', '10000', '--repeats', '3'), 900),
    'ranker-agents': (evaluation('ranker-agents', '--compare-rankers', *RANKERS, '--ranker-agent-check', '--context-window', '65536', '--sizes', '100', '--cases', 'alice-lunch'), 180),
    'discovery-v2': (evaluation('discovery-v2', '--compare-rankers', *RANKERS, '--dataset', 'discovery-v2', '--sizes', '100', '1000', '10000', '--draws', '11', '22', '33', '--repeats', '1'), 5400),
    'live': (evaluation('live', '--compare', '--mode', 'live', '--context-window', '65536', '--sizes', '0', '100', '--cases', 'alice-lunch', 'alice-contract', 'dormant-owner', 'empty-catalog', 'genuinely-new', 'alternating-topics', 'competing-drafts', 'two-owners', '--max-calls', '128', '--case-timeout', '180'), 1800),
}

if __name__ == '__main__':
    name = sys.argv[1]
    command, timeout = COMMANDS[name]
    result_path = HERE / 'checks' / (name + '.json')
    log_path = result_path.with_suffix('.log')
    if result_path.exists() or log_path.exists():
        raise SystemExit('Refusing to overwrite a previous check')
    result = {'check': name, 'command': command, 'cwd': str(ROOT), 'timeout_seconds': timeout,
              'started_utc': datetime.now(timezone.utc).isoformat(), 'log': str(log_path.relative_to(HERE)),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    started = perf_counter()
    with log_path.open('wb') as output:
        try:
            process = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
            result['exit_code'] = process.returncode
        except subprocess.TimeoutExpired:
            result.update(exit_code=None, failure='timeout')
    result.update(finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=perf_counter()-started,
                  log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest())
    result_path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
    lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
    print('\n'.join(lines[-20:]))
    raise SystemExit(result['exit_code'] if result['exit_code'] is not None else 1)
