"""Deterministic trade-outcome learning. Scores are never calibrated probabilities."""
from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timedelta
from statistics import mean,pstdev

from .learning import digest
from .ml import ENRICHED,features,sigmoid
from .models import aware


TRADE_FEATURES=(*ENRICHED,'gross_reward_r','stop_distance_atr','estimated_cost_stop_ratio','side')
LEGACY_TRADE_SET='trade_context_v1'
MA_TRADE_SET='trade_ma_regime_v2'
MA_TRADE_FEATURES=(*TRADE_FEATURES,'side_distance_sma50_atr','side_distance_sma200_atr',
    'side_sma50_slope5_atr','side_sma200_slope5_atr','rsi2_scaled','atr_price_ratio',
    'ma205_available','long_slope_pullback_interaction')
LOGISTIC='trade_outcome_logistic_l2'
LOGISTIC_NET='trade_outcome_logistic_l2_net_gate'
LOGISTIC_INITIAL_RISK='trade_outcome_logistic_l2_initial_risk_gate'
NET_GATE_EPS=1e-6


class InsufficientTradeData(ValueError):
    pass


def base_parameters(parameters):
    return {k:v for k,v in parameters.items() if k not in ('trade_filter','trade_score_threshold')}


def trade_feature_names(feature_set):
    if feature_set==LEGACY_TRADE_SET:return TRADE_FEATURES
    if feature_set==MA_TRADE_SET:return MA_TRADE_FEATURES
    raise ValueError('Unsupported trade feature schema')


def model_feature_set(model):
    feature_set=model.get('feature_set',LEGACY_TRADE_SET)
    if (model.get('schema'),feature_set) not in ((1,LEGACY_TRADE_SET),(2,MA_TRADE_SET)):
        raise ValueError('Unsupported trade feature schema')
    return feature_set


def trade_features(decision,bars,costs,instrument,*,feature_set=LEGACY_TRADE_SET):
    """Only the signal's closed candles, prices, and known execution assumptions."""
    trade_feature_names(feature_set)
    if feature_set==MA_TRADE_SET:
        context=bars[-205:]
        if (not context or any(b.symbol!=decision.symbol or b.seconds!=context[-1].seconds
            or b.source!=context[-1].source or b.ts+timedelta(seconds=b.seconds)>decision.ts for b in context)
            or any(b.ts<=a.ts for a,b in zip(context,context[1:]))):
            raise ValueError('MA context requires compatible closed chronological candles at the signal')
    x=features(bars[-200:],'regime_flow_v2');a=decision.indicators['atr']
    stop=abs(decision.price-decision.stop)
    round_cost=(costs.fee(decision.price,instrument.point_value)+costs.fee(decision.target,instrument.point_value)
        +2*(costs.spread_ticks/2+costs.slippage_ticks)*instrument.tick*instrument.point_value)
    x += [decision.rr,stop/max(a,1e-12),round_cost/max(stop*instrument.point_value,1e-12),
        1. if decision.side=='BUY' else -1.]
    if feature_set==MA_TRADE_SET:
        closes=[b.close for b in context];price=closes[-1];side=1. if decision.side=='BUY' else -1.
        def distance(period):
            return side*(price-mean(closes[-period:]))/max(a,1e-12) if len(closes)>=period else 0.
        def slope(period):
            return side*(mean(closes[-period:])-mean(closes[-period-5:-5]))/max(a,1e-12) if len(closes)>=period+5 else 0.
        recent=closes[-201:];changes=[y-z for z,y in zip(recent,recent[1:])]
        gain=mean(max(0.,v) for v in changes[:2]);loss=mean(max(0.,-v) for v in changes[:2])
        for value in changes[2:]:gain=(gain+max(0.,value))/2;loss=(loss+max(0.,-value))/2
        rsi=100-100/(1+gain/loss) if loss else 100. if gain else 50.
        d50=distance(50);s200=slope(200)
        x += [d50,distance(200),slope(50),s200,rsi/100,a/max(price,1e-12),
            float(len(context)>=205),s200*d50]
    return [max(-50.,min(50.,float(value))) for value in x]


def training_sample_health(samples):
    recent=sorted(samples,key=lambda s:s['signal_at'])[-3000:]
    if any(type(s['label']) is not int or s['label'] not in (0,1) for s in recent):
        raise ValueError('Invalid natural-trade outcome label')
    wins=sum(s['label'] for s in recent);losses=len(recent)-wins
    return {'samples':len(recent),'positive':wins,'nonpositive':losses,
        'eligible':len(recent)>=100 and min(wins,losses)>=20}


def fit_net_head(clean,transformed,risk_budget,*,initial_risk=False):
    if type(risk_budget) not in (int,float) or not math.isfinite(risk_budget) or risk_budget<=0:
        raise ValueError('Net-score training requires a positive finite risk budget')
    targets=[]
    for sample in clean:
        net=sample.get('net')
        if (type(net) not in (int,float) or not math.isfinite(net)
            or int(net>0)!=sample['label']):raise ValueError('Net-score label disagrees with realized net cash')
        denominator=sample.get('initial_stop_cash') if initial_risk else risk_budget
        if (type(denominator) not in (int,float) or not math.isfinite(denominator)
            or not 0<denominator<=risk_budget+1e-7):raise ValueError('Invalid or missing initial stop cash')
        targets.append(net/denominator)
    if not all(math.isfinite(y) for y in targets):raise ValueError('Invalid net-score target scaling')
    center=mean(targets);scale=max(1e-6,pstdev(targets));width=len(transformed[0][0])-1
    weights=[0.]*(width+1)
    # Untrimmed net outcomes; train-only target scaling controls numeric units.
    # Negative tails remain in the target and in every financial evaluation.
    for _ in range(120):
        gradients=[0.]*(width+1)
        for (x,_),target in zip(transformed,targets):
            error=sum(w*v for w,v in zip(weights,x))-(target-center)/scale
            for j in range(width+1):gradients[j]+=error*x[j]
        for j in range(width+1):weights[j]-=.05*(gradients[j]/len(clean)+(.05*weights[j] if j<width else 0.))
    head={'weights':weights,'target_mean_r':center,'target_scale_r':scale,'risk_budget':risk_budget,
        'positive_gate_r':NET_GATE_EPS,'loss':'squared_error_l2','regularization':.05,
        'units':'realized net cash / training risk budget; unvalidated score, not a promise of cash'}
    if initial_risk:head.update(target_basis='initial_stop_cash',
        units='realized net cash / actual initial stop cash including costs; unvalidated score')
    return head


def fit_trade_model(samples,*,parameters,symbol,seconds,source,cutoff,costs,instrument,dataset_sha256,
    with_net_head=False,risk_budget=None,feature_set=LEGACY_TRADE_SET):
    if type(with_net_head) is not bool:raise ValueError('Net-head training must be explicit')
    names=trade_feature_names(feature_set)
    cutoff=aware(cutoff);seen=set();clean=[]
    for sample in samples:
        signal=aware(datetime.fromisoformat(sample['signal_at']))
        available=aware(datetime.fromisoformat(sample['available_at']))
        if signal>=available or available>cutoff:raise ValueError('Trade label was unavailable at the training cutoff')
        if signal in seen:raise ValueError('Repeated entry cannot inflate training samples')
        seen.add(signal)
        x=sample['features'];y=sample['label']
        if len(x)!=len(names) or any(type(v) not in (int,float) or not math.isfinite(v) for v in x):
            raise ValueError('Invalid trade feature vector')
        if type(y) is not int or y not in (0,1):raise ValueError('Trade labels must be realized net outcomes')
        clean.append(sample)
    clean.sort(key=lambda s:s['signal_at'])
    clean=clean[-3000:]
    health=training_sample_health(clean);wins=health['positive']
    if not health['eligible']:
        raise InsufficientTradeData('At least 100 closed natural trades and 20 of each net outcome required')
    width=len(names)
    means=[mean(s['features'][j] for s in clean) for j in range(width)]
    stds=[max(1e-6,pstdev(s['features'][j] for s in clean)) for j in range(width)]
    transformed=[([max(-8.,min(8.,(v-m)/sd)) for v,m,sd in zip(s['features'],means,stds)]+[1.],s['label']) for s in clean]
    prior=wins/len(clean);weights=[0.]*width+[math.log(prior/(1-prior))]
    # Fixed regularization/iterations; all threshold selection happens in later temporal folds.
    for _ in range(120):
        gradients=[0.]*(width+1)
        for x,y in transformed:
            error=sigmoid(sum(w*v for w,v in zip(weights,x)))-y
            for j in range(width+1):gradients[j]+=error*x[j]
        for j in range(width+1):weights[j]-=.05*(gradients[j]/len(clean)+(.05*weights[j] if j<width else 0.))
    model={'schema':1 if feature_set==LEGACY_TRADE_SET else 2,
        'algorithm':LOGISTIC_NET if with_net_head else LOGISTIC,'features':list(names),
        'parameters':base_parameters(parameters),'symbol':symbol,'seconds':seconds,'source':source,
        'training_cutoff':cutoff.isoformat(),'training_samples':len(clean),'training_wins':wins,
        'training_samples_sha256':digest(clean),'dataset_sha256':dataset_sha256,
        'means':means,'stds':stds,'weights':weights,'training_prior':prior,'normalization_floor':1e-6,
        'costs':asdict(costs),'instrument':asdict(instrument),'probability_calibrated':False,
        'target':'positive realized net P&L after modeled costs; natural STOP/TARGET exits only',
        'censoring':'forced end-of-window exits excluded from fitting regardless of sign, included in all financial evaluations',
        'execution_enabled':False}
    if feature_set!=LEGACY_TRADE_SET:model['feature_set']=feature_set
    if with_net_head:model['net_head']=fit_net_head(clean,transformed,risk_budget)
    model['sha256']=digest(model)
    return model


def classification_only_model(model):
    """Exact old classifier from the shared fit, with its own immutable checksum."""
    validate_trade_model(model)
    value=deepcopy(model);value.pop('sha256');value.pop('net_head',None);value['algorithm']=LOGISTIC
    value['sha256']=digest(value)
    return value


def initial_risk_model(model,samples):
    """Change only the net target; require the exact already checked training labels."""
    validate_trade_model(model)
    if model['algorithm']!=LOGISTIC_NET:raise ValueError('Initial-risk variant requires the shared joint fit')
    clean=sorted(samples,key=lambda s:s['signal_at'])[-3000:]
    if len(clean)!=model['training_samples'] or digest(clean)!=model['training_samples_sha256']:
        raise ValueError('Initial-risk labels differ from the checked joint fit')
    transformed=[([max(-8.,min(8.,(v-m)/sd)) for v,m,sd in
        zip(s['features'],model['means'],model['stds'])]+[1.],s['label']) for s in clean]
    value=deepcopy(model);value.pop('sha256');value['algorithm']=LOGISTIC_INITIAL_RISK
    value['net_head']=fit_net_head(clean,transformed,model['net_head']['risk_budget'],initial_risk=True)
    value['sha256']=digest(value)
    validate_trade_model(value)
    return value


def validate_trade_model(model,parameters=None):
    if not isinstance(model,dict):raise ValueError('Trade filter must be a checked JSON model')
    value=dict(model);claimed=value.pop('sha256',None)
    if digest(value)!=claimed:raise ValueError('Trade model checksum mismatch')
    names=trade_feature_names(model_feature_set(model))
    if (model.get('algorithm') not in (LOGISTIC,LOGISTIC_NET,LOGISTIC_INITIAL_RISK)
        or model.get('features')!=list(names) or model.get('probability_calibrated') is not False
        or model.get('execution_enabled') is not False or model.get('normalization_floor')!=1e-6):
        raise ValueError('Unsupported trade-outcome model')
    width=len(names)
    arrays=(model.get('means',[]),model.get('stds',[]),model.get('weights',[]))
    if ([len(x) for x in arrays]!=[width,width,width+1]
        or any(type(v) not in (int,float) or not math.isfinite(v) for x in arrays for v in x)
        or any(not 1e-6<=sd<=50 for sd in arrays[1]) or any(abs(m)>50 for m in arrays[0])
        or any(abs(w)>100 for w in arrays[2])):raise ValueError('Invalid trade model dimensions or scaling')
    if model.get('training_samples',0)<100:raise ValueError('Trade model has insufficient training evidence')
    head=model.get('net_head')
    if model['algorithm'] in (LOGISTIC_NET,LOGISTIC_INITIAL_RISK):
        if not isinstance(head,dict):raise ValueError('Net-score model requires its checked net head')
        values=[head.get(k) for k in ('target_mean_r','target_scale_r','risk_budget','positive_gate_r')]
        weights=head.get('weights')
        if (any(type(v) not in (int,float) or not math.isfinite(v) for v in values)
            or values[1]<1e-6 or values[2]<=0 or values[3]!=NET_GATE_EPS
            or head.get('loss')!='squared_error_l2' or head.get('regularization')!=.05
            or not isinstance(weights,list) or len(weights)!=width+1
            or any(type(w) not in (int,float) or not math.isfinite(w) or abs(w)>100 for w in weights)):
            raise ValueError('Invalid net-score head dimensions, units or scaling')
        basis=head.get('target_basis','risk_budget')
        if basis!=('initial_stop_cash' if model['algorithm']==LOGISTIC_INITIAL_RISK else 'risk_budget'):
            raise ValueError('Net-score target units disagree with model algorithm')
    elif head is not None:raise ValueError('Classifier cannot silently ignore a net head')
    if parameters is not None and model['parameters']!=base_parameters(parameters):
        raise ValueError('Trade model belongs to different entry/stop/target parameters; retrain it')
    aware(datetime.fromisoformat(model['training_cutoff']))


def score_trade(model,decision,bars):
    validate_trade_model(model)
    feature_set=model_feature_set(model);context=205 if feature_set==MA_TRADE_SET else 200
    if not bars or any(b.symbol!=model['symbol'] or b.seconds!=model['seconds'] or b.source!=model['source'] for b in bars[-context:]):
        raise ValueError('Trade model requires compatible market history')
    if decision.ts<=aware(datetime.fromisoformat(model['training_cutoff'])):
        raise ValueError('Trade model cannot read its own training period')
    from .models import ExecutionSettings,Instrument
    args=(decision,bars,ExecutionSettings(**model['costs']),Instrument(**model['instrument']))
    x=trade_features(*args) if feature_set==LEGACY_TRADE_SET else trade_features(*args,feature_set=feature_set)
    z=[(v-m)/sd for v,m,sd in zip(x,model['means'],model['stds'])]
    drift=max(abs(v) for v in z)
    bounded=[max(-8.,min(8.,v)) for v in z]+[1.]
    result={'score':sigmoid(sum(w*v for w,v in zip(model['weights'],bounded))),
        'feature_drift':drift,'abstain':drift>8,'probability_calibrated':False}
    if model['algorithm'] in (LOGISTIC_NET,LOGISTIC_INITIAL_RISK):
        head=model['net_head'];net_score=head['target_mean_r']+head['target_scale_r']*sum(w*v for w,v in zip(head['weights'],bounded))
        if not math.isfinite(net_score):raise ValueError('Net score overflow; no decision is permitted')
        passed=net_score>head['positive_gate_r']
        result.update(net_score_r=net_score,net_gate_passed=passed,abstain=result['abstain'] or not passed)
    return result


def collect_trade_samples(bars,strategy,limits,costs,instruments,*,feature_set=LEGACY_TRADE_SET):
    """Teacher runs the actual PAPER engine; feature capture precedes every fill."""
    if strategy.trade_filter is not None:raise ValueError('Teacher must use only the underlying technical strategy')
    from .backtest import run_backtest
    result=run_backtest(bars,strategy,limits,costs,instruments=instruments,collect_trade_features=True,
        trade_feature_set=feature_set)
    samples=result['trade_training_samples']
    diagnostics={'closed_trades':result['metrics']['trades'],'natural_labels':len(samples),
        'censored_forced_exits':sum(t['exit_reason']=='FLATTEN' for t in result['trades']),
        'teacher_metrics':result['metrics'],'teacher_parameters':asdict(strategy),
        'outcome_review':result['outcome_review']}
    if feature_set!=LEGACY_TRADE_SET:diagnostics['feature_set']=feature_set
    return samples,diagnostics
