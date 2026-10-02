from dataclasses import dataclass
from datetime import datetime,timedelta
@dataclass(frozen=True)
class Req:
    site:str;earliest:datetime;latest:datetime;minutes:int;certified:bool
@dataclass(frozen=True)
class Collector:
    name:str;certified:bool;start:datetime;end:datetime
def _clash(s:datetime,e:datetime,busy:list[tuple[datetime,datetime]])->bool:
    return any(s<b and a<e for a,b in busy)
def assign(reqs:list[Req],people:list[Collector]):
    busy={p.name:[] for p in people};out={}
    for r in sorted(reqs,key=lambda x:(x.latest,x.site)):
        best=None
        for p in people:
            if r.certified and not p.certified:continue
            s=max(r.earliest,p.start)
            deadline=min(r.latest,p.end)
            while s+timedelta(minutes=r.minutes)<=deadline:
                e=s+timedelta(minutes=r.minutes)
                if not _clash(s,e,busy[p.name]):
                    if best is None or s<best[0]:best=(s,p.name)
                    break
                s+=timedelta(minutes=5)
        if best is None:
            need="certified " if r.certified else ""
            raise ValueError(f"no available {need}collector for {r.site}")
        s,n=best;out[r.site]=(n,s);busy[n].append((s,s+timedelta(minutes=r.minutes)))
    return out
