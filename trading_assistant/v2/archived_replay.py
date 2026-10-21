"""Run a preserved PAPER policy in its own original source interpreter."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .data import export_csv
from .learning import digest
from .research import atomic_json


# This harness only transports data and constructs original classes. It does not
# replace any calculation, signal, fill, warmup or accounting implementation.
HARNESS = r'''
import json,sys
from dataclasses import replace
from pathlib import Path
request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
workspace=Path(request['workspace']).resolve()
sys.path.insert(0,str(workspace))
from trading_assistant.v2 import blind_testing,data,models,strategy
for module in (blind_testing,data,models,strategy):
    if not Path(module.__file__).resolve().is_relative_to(workspace):
        raise ValueError('Archived evaluator imported outside preserved source')
version=request['version'];settings=version['assumptions']
limits=models.Limits(**settings['limits']);costs=models.ExecutionSettings(**settings['costs'])
instruments={k:models.Instrument(**v) for k,v in settings['instruments'].items()}
policy=strategy.Strategy(**version['parameters'])
bars=data.CSVProvider(request['bars']).bars();warmup=data.CSVProvider(request['warmup']).bars()
normal,_=blind_testing.blind_replay(iter(bars),warmup=warmup,strategy=policy,
    limits=limits,costs=costs,instruments=instruments,trace_path=request['normal_trace'])
stress,_=blind_testing.blind_replay(iter(bars),warmup=warmup,strategy=policy,
    limits=limits,costs=replace(costs,fee_bps=costs.fee_bps*2,slippage_ticks=costs.slippage_ticks*2),
    instruments=instruments,trace_path=request['stress_trace'])
print(json.dumps({'normal':normal,'stress':stress},allow_nan=False))
'''


def comparison_contract(reference, candidate_assumptions):
    """Keep capital, risk, cost and instrument units identical; policy may change."""
    candidate_assumptions=json.loads(json.dumps(candidate_assumptions,allow_nan=False))
    original=reference['assumptions']
    for section in ('costs','instruments'):
        if original[section]!=candidate_assumptions[section]:
            raise ValueError('Reference comparison changes '+section)
    changed={key:{'reference':original['limits'].get(key),'candidate':candidate_assumptions['limits'].get(key)}
        for key in set(original['limits'])|set(candidate_assumptions['limits'])
        if original['limits'].get(key)!=candidate_assumptions['limits'].get(key)}
    if set(changed)-{'allowed_strategies','min_net_reward_r'}:
        raise ValueError('Reference comparison changes capital or risk limits')
    return {'same_capital_risk_costs_instruments':True,'policy_limit_differences':changed}


def archived_replay(store,version_id,bars,warmup,output):
    """No network or registry changes in the child. Never fall back to new code."""
    version=store.version(version_id)
    source_path=store.directory/'code'/(version['code_id']+'.json')
    sources=json.loads(source_path.read_text(encoding='utf-8'))
    if digest(sources)!=version['code_id']:raise ValueError('Archived source checksum mismatch')
    # The first archives omitted the outer package initializer. A blank initializer
    # supplies import scaffolding without importing the current root application.
    materialized=dict(sources)
    if not any(name.replace('\\','/')=='trading_assistant/__init__.py' for name in materialized):
        materialized['trading_assistant/__init__.py']=''
    workspace=store.source_workspace(materialized)
    expected={name.replace('\\','/') for name in materialized if name.endswith('.py')}
    if {p.relative_to(workspace).as_posix() for p in workspace.rglob('*.py')}!=expected:
        raise ValueError('Unexpected Python file in archived workspace')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    export_csv(bars,output/'bars.csv');export_csv(warmup,output/'warmup.csv')
    request={'workspace':str(workspace),'version':version,'bars':str(output/'bars.csv'),
        'warmup':str(output/'warmup.csv'),'normal_trace':str(output/'normal-decisions.jsonl'),
        'stress_trace':str(output/'stress-decisions.jsonl')}
    atomic_json(output/'request.json',request)
    completed=subprocess.run([sys.executable,'-I','-B','-c',HARNESS,str(output/'request.json')],
        cwd=workspace,capture_output=True,text=True,encoding='utf-8',timeout=600)
    (output/'stderr.txt').write_text(completed.stderr,encoding='utf-8')
    if completed.returncode:raise ValueError('Original reference evaluation failed: '+completed.stderr[-2000:])
    result=json.loads(completed.stdout)
    result['provenance']={'version_id':version_id,'algorithm_code_id':version['code_id'],
        'materialized_workspace_id':digest(materialized),'workspace':str(workspace),
        'harness_sha256':digest(HARNESS),'original_parameters_and_assumptions':True,
        'warmup_implementation':'original archived blind_replay; no source patching'}
    atomic_json(output/'result.json',result)
    return result
