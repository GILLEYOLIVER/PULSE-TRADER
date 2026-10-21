from __future__ import annotations
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from statistics import mean,pstdev
from datetime import datetime,timezone
from .indicators import snapshot

FEATURES=("momentum_atr","trend_atr","rsi_scaled","volatility_ratio")

def features(bars):
    x=snapshot(bars);a=max(x["atr"],1e-12)
    return [x["momentum"]/a,(x["ema_fast"]-x["ema_slow"])/a,x["rsi"]/100,x["volatility_ratio"]]

def sigmoid(z): return 1/(1+math.exp(-max(-30.,min(30.,z))))

def train_temporal(bars,path,horizon=1):
    """Optional small logistic model. Train-only scaling, purged temporal splits; no execution authority."""
    if (len(bars)<200 or type(horizon) is not int or horizon<1 or len({b.symbol for b in bars})!=1
        or len({(b.source,b.seconds) for b in bars})!=1):
        raise ValueError("At least 200 bars from one symbol, source and timeframe required")
    if any(b.ts<=a.ts for a,b in zip(bars,bars[1:])): raise ValueError("History must be chronological")
    n=len(bars);cut1=int(n*.6);cut2=int(n*.8)
    datasets=[]
    for lo,hi in ((34,cut1),(cut1,cut2),(cut2,n)):
        datasets.append([(features(bars[max(0,i-199):i+1]),int(bars[i+horizon].close>bars[i].close),bars[i].ts.isoformat()) for i in range(max(34,lo),hi-horizon)])
    train,val,test=datasets
    if min(map(len,datasets))<20: raise ValueError("Insufficient independent samples for the requested horizon")
    means=[mean(row[0][j] for row in train) for j in range(4)]
    stds=[pstdev(row[0][j] for row in train) or 1. for j in range(4)]
    def transform(x): return [(v-m)/s for v,m,s in zip(x,means,stds)]+[1.]
    weights=[0.]*5
    for _ in range(150):
        gradients=[0.]*5
        for x,y,_ in train:
            z=transform(x);error=sigmoid(sum(w*v for w,v in zip(weights,z)))-y
            for j in range(5): gradients[j]+=error*z[j]
        for j in range(5): weights[j]-=.05*(gradients[j]/len(train)+(.01*weights[j] if j<4 else 0))
    def evaluate(data):
        predicted=[int(sigmoid(sum(w*v for w,v in zip(weights,transform(x))))>=.5) for x,_,_ in data]
        baseline=int(mean(y for _,y,_ in train)>=.5)
        return {"count":len(data),"accuracy":mean(int(p==row[1]) for p,row in zip(predicted,data)),
            "majority_accuracy":mean(int(y==baseline) for _,y,_ in data),
            "momentum_accuracy":mean(int((x[0]>0)==bool(y)) for x,y,_ in data)}
    validation=evaluate(val);testing=evaluate(test)
    # Fit calibration on validation only; the final partition is never used for fitting.
    def raw_logit(x): return sum(w*v for w,v in zip(weights,transform(x)))
    scale,bias=1.,0.
    for _ in range(200):
        ga=gb=0.
        for x,y,_ in val:
            z=raw_logit(x);error=sigmoid(scale*z+bias)-y
            ga+=error*z;gb+=error
        scale-=.02*(ga/len(val)+.01*(scale-1))
        bias-=.02*gb/len(val)
    probabilities=[sigmoid(scale*raw_logit(x)+bias) for x,_,_ in test]
    base_rate=mean(y for _,y,_ in train)
    brier=mean((p-row[1])**2 for p,row in zip(probabilities,test))
    baseline_brier=mean((base_rate-y)**2 for _,y,_ in test)
    bins=[];ece=0.
    for index in range(5):
        group=[(p,row[1]) for p,row in zip(probabilities,test) if min(4,int(p*5))==index]
        if group:
            predicted=mean(p for p,_ in group);observed=mean(y for _,y in group)
            ece+=len(group)/len(test)*abs(predicted-observed)
            bins.append({"count":len(group),"predicted":predicted,"observed":observed})
    real_history=all(not any(tag in b.source.upper() for tag in ("SYNTH", "DEMO", "MOCK")) for b in bars)
    calibrated=real_history and min(len(val),len(test))>=100 and ece<=.05 and brier<baseline_brier
    model={"version":1,"algorithm":"logistic_l2","features":FEATURES,"symbol":bars[0].symbol,"source":bars[0].source,
        "created_at":datetime.now(timezone.utc).isoformat(),
        "seconds":bars[0].seconds,"means":means,"stds":stds,"weights":weights,"train_end":bars[cut1-1].ts.isoformat(),
        "validation":validation,"test":testing,"horizon":horizon,"purge_bars":horizon,
        "adoption_candidate":validation["accuracy"]>max(validation["majority_accuracy"],validation["momentum_accuracy"]),
        "execution_enabled":False,"probability_calibrated":calibrated,
        "calibration":{"method":"platt_validation_only","scale":scale,"bias":bias,"test_brier":brier,
            "baseline_brier":baseline_brier,"test_ece":ece,"test_bins":bins,
            "gate":"non-synthetic, >=100 validation and test samples, ECE <= 0.05, Brier better than prior baseline"},
        "limitation":"Accuracy is not profitability; holdout is evaluated once, synthetic history cannot validate market performance"}
    model["sha256"]=hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest()
    Path(path).write_text(json.dumps(model,indent=2),encoding="utf-8")
    return model

def predict(model,bars):
    copy=dict(model);digest=copy.pop("sha256")
    if hashlib.sha256(json.dumps(copy,sort_keys=True).encode()).hexdigest()!=digest: raise ValueError("Model checksum mismatch")
    if (bars[-1].ts.isoformat()<=model["train_end"]
        or any(b.symbol!=model["symbol"] or b.source!=model["source"] or b.seconds!=model["seconds"] for b in bars)):
        raise ValueError("Inference requires later compatible data")
    x=features(bars);scaled=[(v-m)/s for v,m,s in zip(x,model["means"],model["stds"])]+[1.]
    logit=sum(w*v for w,v in zip(model["weights"],scaled));score=sigmoid(logit)
    drift=max(abs(z) for z in scaled[:-1])
    ind=snapshot(bars)
    calibration=model.get("calibration",{})
    probability=sigmoid(calibration.get("scale",1.)*logit+calibration.get("bias",0.)) if model.get("probability_calibrated") and drift<=4 else None
    return {"class":"UP" if (probability if probability is not None else score)>=.5 else "DOWN","uncalibrated_score":score,"confidence":max(probability,1-probability) if probability is not None else None,
        "probability_up":probability,"probability_calibrated":probability is not None,
        "feature_drift":drift,"degraded":drift>4,"regime":"volatile" if ind["volatility_ratio"]>2 else "trend" if ind["trend_strength"]>.5 else "range"}
