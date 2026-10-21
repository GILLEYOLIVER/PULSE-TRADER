"""Deterministic, auditable research selection. No live routing or desktop adoption."""
from __future__ import annotations

import json
import math
import os
import hashlib
import zipfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path

from .learning import digest
from .strategy import Strategy


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


def wilson(wins,trades):
    if type(wins) is not int or type(trades) is not int or not 0<=wins<=trades:
        raise ValueError('Invalid operation counts')
    if not trades:return [0.,1.]
    z=1.959963984540054;p=wins/trades;denominator=1+z*z/trades
    middle=(p+z*z/(2*trades))/denominator
    distance=z*math.sqrt(p*(1-p)/trades+z*z/(4*trades*trades))/denominator
    return [max(0.,middle-distance),min(1.,middle+distance)]


def plan_forward(rotation,symbol,seconds,*,as_of,test_days,training_days,after=None):
    """Advance in time: never evaluate an earlier market after learning a later one."""
    from datetime import date,timedelta
    first=date(2020,8,15) if symbol=='SOLUSDT' else date(2018,1,1)
    start=max(first+timedelta(days=training_days),date.fromisoformat(after) if after else first)
    last=as_of.date()
    while start+timedelta(days=test_days)<=last:
        end=start+timedelta(days=test_days)
        if rotation.available(symbol,seconds,start.isoformat(),end.isoformat()):
            return {'training_start':(start-timedelta(days=training_days)).isoformat(),
                'test_start':start.isoformat(),'test_end':end.isoformat()}
        start=end
    raise ValueError('Sem janela inédita posterior ao aprendizado; aguarde dados novos ou avance em outro ativo/prazo')


def warmup_start(start,seconds,count=250):
    """Reserve enough past context at every timeframe, plus one day for real gaps."""
    from datetime import timedelta
    if type(seconds) is not int or seconds<=0 or type(count) is not int or count<1:raise ValueError('Invalid warmup size')
    return (start-timedelta(days=math.ceil(seconds*count/86400)+1)).date().isoformat()


def development_slices(bars,after=None):
    """Compare every candidate on identical folds after any frozen model's cutoff."""
    from datetime import datetime
    first=len(bars)//2
    if after:
        cutoff=datetime.fromisoformat(after)
        first=max(first,next((i for i,b in enumerate(bars) if b.ts>=cutoff),len(bars)))
    count=len(bars)-first
    if count<105:return []
    cuts=[first,first+count//3,first+count*2//3,len(bars)]
    return list(zip(cuts,cuts[1:]))


def aggregate_metrics(reports):
    """Weight by actual trades. A no-trade run supplies no accuracy observations."""
    rows=[r['metrics'] if 'metrics' in r else r for r in reports]
    trades=sum(r['trades'] for r in rows)
    wins=sum(round(r['win_rate']*r['trades']) for r in rows)
    return {'trades':trades,'wins':wins,'win_rate':wins/trades if trades else None,
        'net':sum(r['net'] for r in rows),'fees':sum(r.get('fees',0.) for r in rows),
        'max_window_drawdown':max((r['max_drawdown'] for r in rows),default=0.),
        'wilson_95_descriptive':wilson(wins,trades)}


def development_result(parameters,reports):
    combined=aggregate_metrics(reports);metrics=[r['metrics'] for r in reports]
    eligible=(len(metrics)>=3 and combined['trades']>=30
        and all(r['trades']>=5 and r['net']>0 for r in metrics)
        and combined['max_window_drawdown']<=10000 and all(r['passed'] for r in reports))
    return {'parameters':parameters,'folds':metrics,'aggregate':combined,'eligible':eligible,
        'selection_key':[combined['wilson_95_descriptive'][0],
            min((r['expectancy'] for r in metrics),default=0.),combined['net']-.5*combined['max_window_drawdown']]}


def select_development(results,reference):
    eligible=[r for r in results if r['eligible']]
    if not eligible:return reference,'INSUFFICIENT_CONSISTENT_DEVELOPMENT'
    winner=max(eligible,key=lambda r:tuple(r['selection_key']))
    if reference['eligible'] and tuple(winner['selection_key'])<=tuple(reference['selection_key']):
        return reference,'REFERENCE_RETAINED'
    return winner,'CANDIDATE_FROZEN_BEFORE_EXTERNAL'


def promotion_decision(development,candidate,reference,stress):
    """One preselected challenger; the holdout is a rejection gate, not a grid search."""
    c=candidate['metrics'];r=reference['metrics'];s=stress['metrics'];reasons=[]
    if not development['eligible']:reasons.append('insufficient_consistent_development')
    if not all(x['passed'] for x in (candidate,reference,stress)):reasons.append('mechanical_check_failed')
    if c['trades']<10:reasons.append('fewer_than_10_external_trades')
    if c['net']<=0 or s['net']<=0:reasons.append('nonpositive_net_or_cost_stress')
    if c['max_drawdown']>10000 or s['max_drawdown']>10000:reasons.append('drawdown_above_10_percent')
    if c['net']<=r['net']:reasons.append('no_net_improvement_over_reference')
    if c['win_rate']<r['win_rate']:reasons.append('accuracy_worse_than_reference')
    return {'promoted':not reasons,'reasons':reasons}


def goal_evidence(records):
    """Only unchanged versions and disjoint real windows qualify an observed goal."""
    usable=[];windows=[];version=None
    for record in records:
        if not record.get('real_history') or not record.get('passed') or not record.get('qualified_for_goal',True):continue
        current=record['version_id']
        if version is not None and current!=version:raise ValueError('Cannot combine different versions for confirmation')
        version=current
        start,end=record['start'],record['end']
        if start>=end or any(start<b and a<end for a,b in windows):
            raise ValueError('Confirmation windows must be disjoint')
        windows.append((start,end));usable.append(record)
    combined=aggregate_metrics([r['metrics'] for r in usable])
    reached=(len(usable)>=3 and combined['trades']>=100
        and all(r['metrics']['trades']>=10 and r['metrics']['win_rate']>.9
            and r['metrics']['net']>0 and r['stress_net']>0
            and r['metrics']['max_drawdown']<=10000 and r['stress_drawdown']<=10000 for r in usable))
    return {'observed_goal_reached':reached,'version_id':version,'windows':len(usable),**combined,
        'meaning':'Observed closed-operation results only; no guaranteed future accuracy or multiple-testing-adjusted inference'}


def candidate_bank(cycle_index,reference,limit=30):
    """Rotate an a-priori bounded grid; external outcomes do not set thresholds."""
    methods=('trend','breakout','pullback','adaptive','sma_cross','ema_pullback','mean_reversion')
    filters=({},
        {'min_trend_atr':.35,'min_efficiency':.2,'min_relative_volume':.8,'max_entry_atr':1.5,'require_trend_slope':True},
        {'min_trend_atr':.65,'min_efficiency':.35,'min_relative_volume':1.,'max_entry_atr':1.,'require_trend_slope':True})
    bank=[asdict(Strategy(method,reward,stop,**filter_config)) for reward in (.5,1.,1.25,2.,3.)
        for stop in (1.5,2.5) for filter_config in filters for method in methods]
    bank=[bank[(i*37)%len(bank)] for i in range(len(bank))]
    offset=(cycle_index*limit)%len(bank);rotated=bank[offset:]+bank[:offset]
    result=[];seen=set()
    for parameters in [reference,asdict(Strategy()),*rotated]:
        key=digest(parameters)
        if key not in seen:result.append(parameters);seen.add(key)
        if len(result)>=limit:break
    return result


class ChampionStore:
    """Immutable versions + checked atomic reference. Never writes paper.sqlite."""
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.state_path=self.directory/'state.json'

    @contextmanager
    def lock(self):
        path=self.directory/'cycle.lock'
        try:descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:raise ValueError('A research cycle already owns the registry; inspect cycle.lock before recovery') from None
        try:
            os.write(descriptor,str(os.getpid()).encode());os.close(descriptor)
            yield
        finally:path.unlink()

    def state(self):
        if not self.state_path.exists():return {'schema':1,'groups':{},'completed_cycles':0,'evaluations':[]}
        value=json.loads(self.state_path.read_text(encoding='utf-8'));claimed=value.pop('sha256')
        if digest(value)!=claimed:raise ValueError('Research registry checksum mismatch')
        return value

    def save(self,value):atomic_json(self.state_path,{**value,'sha256':digest(value)})

    def archive_source(self,sources):
        code=digest(sources);path=self.directory/'code'/(code+'.json')
        if path.exists():
            if json.loads(path.read_text(encoding='utf-8'))!=sources:raise ValueError('Code archive altered')
        else:atomic_json(path,sources)
        return code

    def source_workspace(self,sources):
        code=self.archive_source(sources);root=self.directory/'workspaces'/code
        for name,content in sources.items():
            path=root/name
            if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Source archive path escapes workspace')
            if path.exists():
                if path.read_text(encoding='utf-8')!=content:raise ValueError('Frozen source workspace altered')
            else:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content,encoding='utf-8',newline='\n')
        return root.resolve()

    def archive_run(self,group_directory):
        """Mirror reports AND raw data in runtime so ordinary backups include them."""
        root=Path(group_directory).resolve()
        path=self.directory/'runs'/(root.parent.name+'-'+root.name+'.zip')
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():raise ValueError('Completed research bundle already exists; never overwrite it')
        temporary=path.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(root.rglob('*')):
                if source.is_file():
                    if source.is_symlink() or not source.resolve().is_relative_to(root):raise ValueError('Research bundle cannot include external files')
                    archive.write(source,source.relative_to(root).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:raise ValueError('Research bundle integrity failed')
        temporary.replace(path)
        checksum=hashlib.sha256(path.read_bytes()).hexdigest()
        atomic_json(path.with_suffix('.manifest.json'),{'sha256':checksum,'bytes':path.stat().st_size,'source':str(root)})
        return str(path.resolve())

    def register(self,group,parameters,code_id,assumptions):
        Strategy(**parameters)
        version=json.loads(json.dumps({'schema':1,'group':group,'parameters':parameters,
            'code_id':code_id,'assumptions':assumptions},allow_nan=False))
        version_id=digest(version);path=self.directory/'versions'/(version_id+'.json')
        if path.exists():
            if json.loads(path.read_text(encoding='utf-8'))!=version:raise ValueError('Version artifact altered')
        else:atomic_json(path,version)
        return version_id

    def version(self,version_id):
        if len(version_id)!=64 or any(c not in '0123456789abcdef' for c in version_id):raise ValueError('Invalid version id')
        value=json.loads((self.directory/'versions'/(version_id+'.json')).read_text(encoding='utf-8'))
        if digest(value)!=version_id:raise ValueError('Version artifact checksum mismatch')
        return value

    def set_champion(self,state,group,version_id,reason):
        if self.version(version_id)['group']!=group:raise ValueError('Champion belongs to another asset/timeframe')
        item=state['groups'].setdefault(group,{'champion':None,'history':[],'cycles':0})
        previous=item['champion']
        if previous!=version_id:
            item['history'].append({'previous':previous,'version':version_id,'reason':reason,
                'at':datetime.now(timezone.utc).isoformat()})
            item['champion']=version_id
        return previous

    def validated_reference(self,state,group):
        """A source rebase is not a successful trading-policy promotion."""
        item=state['groups'][group];anchor=None
        accepted={'INITIAL_REFERENCE','VALIDATION_AND_EXTERNAL_GATE_PASSED'}
        repairs={'REFERENCE_PARAMETERS_REEVALUATED_ON_NEW_CODE','RESTORED_ORIGINAL_ARCHIVED_REFERENCE'}
        for row in item['history']:
            if row['reason'] in accepted:anchor=row['version']
            elif row['reason'] not in repairs:
                raise ValueError('Unrecognized champion history; original reference requires review')
        if anchor is None:raise ValueError('No original or validated reference in history')
        if self.version(anchor)['group']!=group:raise ValueError('Reference history belongs to another group')
        return anchor
