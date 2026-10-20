from __future__ import annotations
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from statistics import mean,pstdev
from .indicators import snapshot

FEATURES=("momentum_atr","trend_atr","rsi_scaled","volatility_ratio")

def features(bars):
    x=snapshot(bars);a=max(x["atr"],1e-12)
    return [x["momentum"]/a,(x["ema_fast"]-x["ema_slow"])/a,x["rsi"]/100,x["volatility_ratio"]]

def sigmoid(z): return 1/(1+math.exp(-max(-30.,min(30.,z))))

def train_temporal(bars,path,horizon=1):
    """Optional small logistic model. Train-only scaling, purged temporal splits; no execution authority."""
    if len(bars)<200 or horizon<1 or len({b.symbol for b in bars})!=1: raise ValueError("At least 200 single-symbol bars required")
    if any(b.ts<=a.ts for a,b in zip(bars,bars[1:])): raise ValueError("History must be chronological")
    n=len(bars);cut1=int(n*.6);cut2=int(n*.8)
    datasets=[]
    for lo,hi in ((34,cut1),(cut1,cut2),(cut2,n)):
        datasets.append([(features(bars[max(0,i-199):i+1]),int(bars[i+horizon].close>bars[i].close),bars[i].ts.isoformat()) for i in range(max(34,lo),hi-horizon)])
    train,val,test=datasets
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
    model={"version":1,"algorithm":"logistic_l2","features":FEATURES,"symbol":bars[0].symbol,"source":bars[0].source,
        "seconds":bars[0].seconds,"means":means,"stds":stds,"weights":weights,"train_end":bars[cut1-1].ts.isoformat(),
        "validation":validation,"test":testing,"horizon":horizon,"purge_bars":horizon,
        "adoption_candidate":validation["accuracy"]>max(validation["majority_accuracy"],validation["momentum_accuracy"]),
        "execution_enabled":False,"probability_calibrated":False,
        "limitation":"Accuracy is not profitability; holdout is evaluated once, synthetic history cannot validate market performance"}
    model["sha256"]=hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest()
    Path(path).write_text(json.dumps(model,indent=2),encoding="utf-8")
    return model

def predict(model,bars):
    copy=dict(model);digest=copy.pop("sha256")
    if hashlib.sha256(json.dumps(copy,sort_keys=True).encode()).hexdigest()!=digest: raise ValueError("Model checksum mismatch")
    if (bars[-1].ts.isoformat()<=model["train_end"] or bars[-1].symbol!=model["symbol"]
        or bars[-1].source!=model["source"] or bars[-1].seconds!=model["seconds"]):
        raise ValueError("Inference requires later compatible data")
    x=features(bars);scaled=[(v-m)/s for v,m,s in zip(x,model["means"],model["stds"])]+[1.]
    score=sigmoid(sum(w*v for w,v in zip(model["weights"],scaled)))
    drift=max(abs(z) for z in scaled[:-1])
    ind=snapshot(bars)
    return {"class":"UP" if score>=.5 else "DOWN","uncalibrated_score":score,"confidence":None,
        "feature_drift":drift,"degraded":drift>4,"regime":"volatile" if ind["volatility_ratio"]>2 else "trend" if ind["trend_strength"]>.5 else "range"}
