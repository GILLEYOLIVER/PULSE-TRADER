"""Local append-only experiment memory. Blind evaluation never enters training memory."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime,timezone
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class LearningMemory:
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.training_path=self.directory/'memoria_treinamento.jsonl'
        self.evaluation_path=self.directory/'avaliacoes_cegas.jsonl'
        for path in (self.training_path,self.evaluation_path):path.touch(exist_ok=True)

    def _read(self,path):
        previous='0'*64;records=[]
        with path.open(encoding='utf-8') as stream:
            for sequence,line in enumerate(stream,1):
                if len(line)>1_000_000:raise ValueError('Registro de aprendizado acima do limite')
                record=json.loads(line);claimed=record.pop('sha256',None)
                if record.get('sequence')!=sequence or record.get('previous')!=previous or digest(record)!=claimed:
                    raise ValueError('Memória de aprendizado alterada ou incompleta; preserve o arquivo e revise')
                record['sha256']=claimed;records.append(record);previous=claimed
        return records

    def append(self,kind,payload):
        if kind not in ('TRAIN','VALIDATION','BLIND_TEST','SEALED_POLICY'):raise ValueError('Tipo de experiência desconhecido')
        path=self.evaluation_path if kind=='BLIND_TEST' else self.training_path
        lock=self.directory/'memory.lock'
        try:descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:raise ValueError('Outra gravação de aprendizado está em andamento') from None
        try:
            os.close(descriptor)
            records=self._read(path)
            record={'schema':1,'sequence':len(records)+1,'previous':records[-1]['sha256'] if records else '0'*64,
                'kind':kind,'recorded_at':datetime.now(timezone.utc).isoformat(),'payload':payload}
            record['sha256']=digest(record)
            raw=(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
            if len(raw)>1_000_000:raise ValueError('Grave métricas e caminhos, não todo o histórico dentro da memória')
            with path.open('ab') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            return record
        finally:lock.unlink()

    def training_records(self):
        records=self._read(self.training_path)
        if any(record['kind']=='BLIND_TEST' for record in records):raise ValueError('Avaliação cega não pode treinar o algoritmo')
        return records

    def evaluations(self):return self._read(self.evaluation_path)

    def parameter_priors(self,profile,limit=3):
        result=[];seen=set()
        for record in reversed(self.training_records()):
            payload=record['payload'];winner=payload.get('winner',{})
            if record['kind']!='SEALED_POLICY' or payload.get('profile')!=profile or 'parameters' not in winner:continue
            key=digest({'parameters':winner['parameters'],'risk_profile':winner['risk_profile']})
            if key in seen:continue
            seen.add(key);result.append({'parameters':winner['parameters'],'risk_profile':winner['risk_profile']})
            if len(result)>=limit:break
        return result

    def remember_model(self,bars,model,path):
        from .suggestions import history_digest
        from .data import export_csv
        dataset=history_digest(bars)
        datasets=self.directory/'datasets';datasets.mkdir(exist_ok=True)
        dataset_path=datasets/(dataset+'.csv')
        if not dataset_path.exists():export_csv(bars,dataset_path)
        models=self.directory/'models';models.mkdir(exist_ok=True)
        model_path=models/(model['sha256']+'.json')
        if not model_path.exists():model_path.write_text(json.dumps(model,indent=2,allow_nan=False),encoding='utf-8')
        from datetime import timedelta,time
        end=bars[-1].ts+timedelta(seconds=bars[-1].seconds)
        end_date=end.date()+timedelta(days=int(end.time().replace(tzinfo=None)!=time(0)))
        HistoricalRotation(self.directory).mark_development(bars[0].symbol,bars[0].seconds,
            bars[0].ts.date().isoformat(),end_date.isoformat(),dataset)
        return self.append('TRAIN',{'dataset_sha256':dataset,'dataset_path':str(dataset_path.relative_to(self.directory)),'symbol':bars[0].symbol,
            'source':bars[0].source,'seconds':bars[0].seconds,'candles':len(bars),
            'first':bars[0].ts.isoformat(),'last':bars[-1].ts.isoformat(),
            'feature_set':model.get('feature_set','legacy'),'model_sha256':model['sha256'],
            'model_path':str(model_path.relative_to(self.directory)),'original_export_path':str(path),'training_cutoff':model['train_end'],
            'validation':model['validation'],'internal_test':model['test'],
            'execution_enabled':False,'purpose':'Treino temporal; distinto da avaliação cega externa'})


class HistoricalRotation:
    """Reserve disjoint external windows; known history can be used only as development/regression."""
    def __init__(self,directory):
        self.path=Path(directory)/'historicos_utilizados.json'
        self.path.parent.mkdir(parents=True,exist_ok=True)

    def records(self):
        if not self.path.exists():return []
        value=json.loads(self.path.read_text(encoding='utf-8'))
        expected=value.pop('sha256',None)
        if digest(value)!=expected or value.get('schema')!=1:raise ValueError('Historical rotation registry checksum mismatch')
        return value['windows']

    def available(self,symbol,seconds,start,end):
        return not any(row['symbol']==symbol and row['seconds']==seconds and start<row['end'] and row['start']<end for row in self.records())

    def mark_development(self,symbol,seconds,start,end,run_id):
        records=self.records()
        item={'run_id':run_id,'symbol':symbol,'seconds':seconds,'start':start,'end':end,'role':'DEVELOPMENT'}
        if item in records:return
        records.append(item)
        value={'schema':1,'windows':records};value['sha256']=digest(value)
        temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2),encoding='utf-8');temporary.replace(self.path)

    def reserve(self,run_id,symbol,seconds,start,end):
        from datetime import date
        if date.fromisoformat(start)>=date.fromisoformat(end):raise ValueError('Historical window must advance')
        records=self.records()
        if any(row['run_id']==run_id and (row['symbol'],row['seconds'],row['start'],row['end'])==(symbol,seconds,start,end) for row in records):return
        if not self.available(symbol,seconds,start,end):raise ValueError('Historical window was already used; select another period or mark the run as regression')
        records.append({'run_id':run_id,'symbol':symbol,'seconds':seconds,'start':start,'end':end,'role':'EXTERNAL_EVALUATION'})
        value={'schema':1,'windows':records};value['sha256']=digest(value)
        temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2),encoding='utf-8');temporary.replace(self.path)

    def plan(self,symbols,seconds,*,as_of,test_days,training_days):
        from datetime import timedelta,date
        end=as_of.date()
        for _ in range(120):
            start=end-timedelta(days=test_days)
            train=start-timedelta(days=training_days)
            if train<date(2018,1,1):break
            if all(self.available(symbol,seconds,start.isoformat(),end.isoformat()) for symbol in symbols):
                return {'training_start':train.isoformat(),'test_start':start.isoformat(),'test_end':end.isoformat()}
            end=start
        raise ValueError('Sem janela histórica inédita suficiente; aguarde novos dados ou use outro ativo. Histórico conhecido só pode ser regressão/desenvolvimento.')
