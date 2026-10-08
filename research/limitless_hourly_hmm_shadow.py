#!/usr/bin/env python3
"""One fixed Gaussian two-state HMM on closed returns; reuse same-event paper replay."""
import argparse
import contextlib
import io
import json
import math
import pathlib

import limitless_hourly_markov_shadow as base


def filtered(returns,variance,transition):
    emissions=[]
    for ret in returns:
        logp=[-.5*(math.log(2*math.pi*v)+ret*ret/v) for v in variance]
        peak=max(logp)
        emissions.append([math.exp(v-peak) for v in logp])
    alpha=[];scale=[]
    for t,emit in enumerate(emissions):
        prior=[.5,.5] if t==0 else [alpha[-1][0]*transition[0][j]+alpha[-1][1]*transition[1][j] for j in (0,1)]
        value=[prior[j]*emit[j] for j in (0,1)]
        norm=sum(value)
        if norm<=0:raise ValueError('HMM_ZERO_FORWARD_MASS')
        alpha.append([v/norm for v in value]);scale.append(norm)
    beta=[[1.,1.] for _ in returns]
    for t in range(len(returns)-2,-1,-1):
        beta[t]=[sum(transition[i][j]*emissions[t+1][j]*beta[t+1][j] for j in (0,1))/scale[t+1] for i in (0,1)]
    gamma=[];xi=[]
    for t,(a,b) in enumerate(zip(alpha,beta)):
        g=[a[i]*b[i] for i in (0,1)];norm=sum(g)
        gamma.append([v/norm for v in g])
        if t<len(returns)-1:
            z=[[a[i]*transition[i][j]*emissions[t+1][j]*beta[t+1][j] for j in (0,1)] for i in (0,1)]
            mass=sum(map(sum,z))
            xi.append([[v/mass for v in row] for row in z])
    return alpha[-1],gamma,xi


def hmm_probability(candles,current,opening,now,available_before,end):
    cutoff=min(now,available_before)
    closed=sorted((r for r in candles if float(r[6])/1000<cutoff),key=lambda r:r[0])[-121:]
    if len(closed)!=121 or any(int(r[6])-int(r[0])!=59999 for r in closed) or any(int(b[0])-int(a[0])!=60000 for a,b in zip(closed,closed[1:])):
        raise ValueError('MISSING_CLOSED_WARMUP')
    if now-float(closed[-1][6])/1000>120:raise ValueError('STALE_CANDLES')
    prices=[float(r[4]) for r in closed]
    if not all(math.isfinite(p) and p>0 for p in prices):raise ValueError('INVALID_CANDLES')
    returns=[math.log(b/a) for a,b in zip(prices,prices[1:])]
    baseline=sum(r*r for r in returns)/len(returns)
    if not math.isfinite(baseline) or baseline<=0:raise ValueError('INVALID_BASE_VARIANCE')
    low,high=baseline*.05,baseline*20
    variance=[baseline*.25,baseline*4]
    transition=[[.9,.1],[.1,.9]]
    priors=[[4,1],[1,4]]
    for _ in range(20):
        _,gamma,xi=filtered(returns,variance,transition)
        transition=[[ (priors[i][j]+sum(z[i][j] for z in xi)) /
                      (sum(priors[i])+sum(sum(z[i]) for z in xi)) for j in (0,1)] for i in (0,1)]
        variance=[max(low,min(high,(10*baseline+sum(g[i]*r*r for g,r in zip(gamma,returns))) /
                              (10+sum(g[i] for g in gamma)))) for i in (0,1)]
    state,_,_=filtered(returns,variance,transition)
    if variance[0]>variance[1]:
        variance.reverse()
        transition=[[transition[1][1],transition[1][0]],[transition[0][1],transition[0][0]]]
        state.reverse()
    filtered_high=state[1]
    remaining=(end-now)/60
    if remaining<=0:raise ValueError('EXPIRED_MARKET')
    total=0.
    while remaining>0:
        state=[state[0]*transition[0][0]+state[1]*transition[1][0],
               state[0]*transition[0][1]+state[1]*transition[1][1]]
        weight=min(1.,remaining)
        total+=weight*(state[0]*variance[0]+state[1]*variance[1])
        remaining-=weight
    if total<=0 or not math.isfinite(total):raise ValueError('INVALID_FORECAST_VARIANCE')
    p=.5*(1+math.erf(math.log(current/float(opening))/math.sqrt(total*2)))
    return p,variance,transition,filtered_high,total


def rename_keys(value):
    if isinstance(value,dict):return {k.replace('markov','hmm'):rename_keys(v) for k,v in value.items()}
    if isinstance(value,list):return [rename_keys(x) for x in value]
    return value


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='hmm_shadow_evidence.json')
    parser.add_argument('--cache',default='artifact-cache')
    args=parser.parse_args()
    base.markov_probability=hmm_probability
    with contextlib.redirect_stdout(io.StringIO()) as log:
        base.main()
    for line in log.getvalue().splitlines():
        if line.startswith('validated_archives='):print(line,flush=True)
    path=pathlib.Path(args.output)
    evidence=rename_keys(json.loads(path.read_text()))
    evidence['schema']='limitless-hourly-hmm-volatility-shadow-v1'
    evidence['protocol']='research/LIMITLESS_HOURLY_HMM_PROTOCOL_2026-10-08.md'
    evidence['limitations']='Fixed two-state Gaussian HMM, same original first event/attempt; old inspected holdout; paper quotes not fills.'
    for row in evidence['rows']:
        row['filtered_high_probability']=row.pop('last_state',None)
    path.write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence['summary'],indent=2))


if __name__=='__main__':main()
