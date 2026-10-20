from __future__ import annotations
import json
from datetime import datetime,timezone
from typing import Any,Dict
from trading_assistant.config import AuditConfig

def redact(value):
    if isinstance(value,dict):
        return {k:"[REDACTED]" if any(token in k.lower() for token in ("key","secret","password","token")) else redact(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [redact(v) for v in value]
    return value

class AuditLogger:
    def __init__(self,config:AuditConfig):self.config=config
    def info(self,event:str,payload:Dict[str,Any]):
        if not self.config.enabled:return
        record={"ts":datetime.now(timezone.utc).isoformat(),"event":event,"payload":redact(payload)}
        with open(self.config.path,"a",encoding="utf-8") as f:
            f.write(json.dumps(record,ensure_ascii=False,default=str,allow_nan=False)+"\n")
