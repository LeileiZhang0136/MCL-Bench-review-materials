"""Recompute matched three-judge descriptive statistics; no API or human labels."""
import argparse,csv,json
from pathlib import Path
from collections import Counter,defaultdict
HERE=Path(__file__).resolve().parent
JUDGES={'gpt52_score':'GPT-5.2','claude_score':'Claude-Opus-4.6 Thinking','gemini_score':'Gemini-3.1-Pro-Preview (High)'}

def calculate():
 rows=list(csv.DictReader((HERE/'matched_three_judge_100.csv').open()));assert len(rows)==100
 assert len({(r['task_id'],r['inference_model']) for r in rows})==100
 for r in rows:
  for k in JUDGES:r[k]=int(r[k]);assert r[k] in (0,1)
  assert len(r['response_sha256'])==64 and len(r['rubrics_sha256'])==64
 rates={name:{'passes':sum(r[k] for r in rows),'responses':100,'pass_percent':sum(r[k] for r in rows)} for k,name in JUDGES.items()}
 patterns=Counter(''.join(str(r[k]) for k in JUDGES) for r in rows)
 pairs=[]
 for a,b in [('gpt52_score','claude_score'),('gpt52_score','gemini_score'),('claude_score','gemini_score')]:
  c=Counter(str(r[a])+str(r[b]) for r in rows);agree=c['00']+c['11'];pa=sum(r[a] for r in rows)/100;pb=sum(r[b] for r in rows)/100;pe=pa*pb+(1-pa)*(1-pb)
  pairs.append({'judge_a':JUDGES[a],'judge_b':JUDGES[b],'counts_a_b':{k:c[k] for k in ['00','01','10','11']},'agreement_percent':agree,'cohens_kappa':(agree/100-pe)/(1-pe) if pe<1 else None,'positive_agreement':2*c['11']/(2*c['11']+c['10']+c['01']) if 2*c['11']+c['10']+c['01'] else None,'negative_agreement':2*c['00']/(2*c['00']+c['10']+c['01']) if 2*c['00']+c['10']+c['01'] else None})
 bymodel={}
 for model in sorted({r['inference_model'] for r in rows}):
  rr=[r for r in rows if r['inference_model']==model];bymodel[model]={'responses':len(rr),'judge_passes':{name:sum(r[k] for r in rr) for k,name in JUDGES.items()}}
 counts={'models':dict(Counter(r['inference_model'] for r in rows)),'categories':dict(Counter(r['category'] for r in rows)),'source_tracks':dict(Counter(r['source_track'] for r in rows)),'unique_cases':len({r['case_id'] for r in rows}),'unique_tasks':len({r['task_id'] for r in rows})}
 return {'scope':'Descriptive comparison on an outcome-blind stratified sample of existing matched responses, not the historical author-review sample. No human accuracy is inferred.','responses':100,'judge_results':rates,'three_way_patterns_gpt_claude_gemini':dict(sorted(patterns.items())),'three_way_agreement_percent':patterns['000']+patterns['111'],'pairwise':pairs,'by_inference_model':bymodel,'sample_composition':counts}

def main(out):
 out.mkdir(parents=True,exist_ok=True);d=calculate();(out/'matched_sample_summary.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
 lines=['# Matched three-judge comparison','','This is a new offline analysis of existing judgments, not the historical 100-response author review.','All judges saw identical response text and rubrics for each included item.','','| Judge | Passed / 100 | Pass rate |','|---|---:|---:|']
 for name,v in d['judge_results'].items():lines.append(f"| {name} | {v['passes']} | {v['pass_percent']:.1f}% |")
 lines+=['',f"All three judges agree on {d['three_way_agreement_percent']}/100 responses.",'','| Judge pair | Agreement | Cohen kappa |','|---|---:|---:|']
 for p in d['pairwise']:lines.append(f"| {p['judge_a']} / {p['judge_b']} | {p['agreement_percent']:.1f}% | {p['cohens_kappa']:.3f} |")
 lines+=['','## Per-model composition','','| Inference model | Responses | GPT passes | Claude passes | Gemini passes |','|---|---:|---:|---:|---:|']
 for model,v in d['by_inference_model'].items():lines.append(f"| {model} | {v['responses']} | "+' | '.join(str(v['judge_passes'][j]) for j in JUDGES.values())+' |')
 lines+=['','## Interpretation','','This is a deliberately stratified sample; the reported values describe this sample rather than population-calibrated accuracy.','Agreement among automated judges is not judge-human agreement.','No ranking stability or independence of self-preference is inferred from 12–13 responses per inference model.','Complete pairwise tables, positive/negative agreement, and sample composition are provided in matched_sample_summary.json.']
 (out/'MATCHED_SAMPLE.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'responses':100,'judges':d['judge_results'],'three_way_agreement':d['three_way_agreement_percent'],'patterns':d['three_way_patterns_gpt_claude_gemini']},ensure_ascii=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=HERE);main(p.parse_args().output_dir)
