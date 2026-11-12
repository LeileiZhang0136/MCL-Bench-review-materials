"""Offline reproduction from public anonymous score rows; no API, private files or packages."""
import argparse,csv,json,math,random
from collections import defaultdict,Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent

def wilson(k,n):
 z=1.959963984540054;p=k/n;den=1+z*z/n
 c=(p+z*z/(2*n))/den;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return [100*(c-h),100*(c+h)]

def main(out):
 out.mkdir(parents=True,exist_ok=True)
 rows=list(csv.DictReader((HERE/'main_model_task_scores.csv').open()))
 assert len(rows)==8640
 seen=set();models=defaultdict(list);tasks={}
 for r in rows:
  key=(r['model'],r['task_id']);assert key not in seen;seen.add(key)
  r['score']=int(r['effective_score']);r['turn']=int(r['turn_index']);r['nr']=int(r['rubric_entry_count'])
  r['status']=json.loads(r['requirement_status_json']);r['matched']=bool(r['status']) and len(r['status'])==r['nr']
  assert r['score'] in (0,1)
  assert r['task_id']==r['case_id']+'/T'+str(r['turn'])
  if r['score_available']=='1':assert int(r['stored_score'])==r['score']
  else:assert r['stored_score']=='' and r['score']==0
  models[r['model']].append(r)
  tasks.setdefault(r['task_id'],{'track':r['source_track'],'any8':False,'any10':False})
  tasks[r['task_id']]['any8']|=bool(r['score']);tasks[r['task_id']]['any10']|=bool(r['score'])
 assert len(models)==8 and len(tasks)==1080
 summaries=[];issues=[]
 for model,rr in models.items():
  cases=defaultdict(list)
  for r in rr:cases[r['case_id']].append(r)
  assert len(cases)==344 and len(rr)==1080
  first=[r for r in rr if r['turn']==1];matched=[r for r in rr if r['matched']]
  k=sum(r['score'] for r in rr);firstk=sum(r['score'] for r in first)
  yes=sum(r['status'].count('yes') for r in matched);nr=sum(r['nr'] for r in matched)
  normalized=k;buckets={}
  for lo,hi,label in [(1,4,'1-4'),(5,8,'5-8'),(9,12,'9-12'),(13,100000,'13+')]:
   group=[r for r in rr if lo<=r['nr']<=hi];buckets[label]={'tasks':len(group),'passed':sum(r['score'] for r in group)}
  for r in rr:
   if r['matched'] and r['score_available']=='1' and r['score']!=int(all(s=='yes' for s in r['status'])):
    normalized+=int(all(s=='yes' for s in r['status']))-r['score']
    issues.append({'model':model,'task_id':r['task_id'],'stored_score':r['score'],'statuses':r['status']})
  summaries.append({'model':model,'cases':344,'tasks':1080,'passed':k,'task_micro_percent':100*k/1080,'wilson_95_percent':wilson(k,1080),'first_turn_passed':firstk,'first_turn_tasks':344,'first_turn_percent':100*firstk/344,'context_macro_percent':100*sum(sum(r['score'] for r in cr)/len(cr) for cr in cases.values())/344,'score_missing_tasks':sum(r['score_available']=='0' for r in rr),'count_aligned_tasks':len(matched),'count_unaligned_or_empty_tasks':1080-len(matched),'aligned_rubrics_yes':yes,'aligned_rubrics_total':nr,'aligned_rubric_satisfaction_percent':100*yes/nr,'aligned_single_failure_tasks':sum(r['score']==0 and r['nr']-r['status'].count('yes')==1 for r in matched),'status_normalized_passed':normalized,'rubric_count_buckets':buckets})
 pairs=[]
 for family in ['Opus','Sonnet']:
  base=f'Claude-{family}-4.6';thinking=base+' Thinking';a={r['task_id']:r for r in models[base]};b={r['task_id']:r for r in models[thinking]};vectors=defaultdict(lambda:[0,0]);paired=Counter()
  for task,r in a.items():
   delta=b[task]['score']-r['score'];vectors[r['case_id']][0]+=delta;vectors[r['case_id']][1]+=1;paired[str(r['score'])+str(b[task]['score'])]+=1
  vv=[tuple(vectors[k]) for k in sorted(vectors)];rng=random.Random(23049);samples=[]
  for _ in range(10000):
   selected=rng.choices(vv,k=344);samples.append(100*sum(v[0] for v in selected)/sum(v[1] for v in selected))
  samples.sort();pairs.append({'base':base,'thinking':thinking,'base_thinking_pair_counts':dict(sorted(paired.items())),'difference_percentage_points':100*sum(v[0] for v in vv)/1080,'case_cluster_bootstrap_95_percentage_points':[samples[249],samples[9749]],'resamples':10000,'seed':23049})
 kimi=HERE.parent/'open_weight_models/open_model_task_scores.csv'
 for r in csv.DictReader(kimi.open()):
  assert r['task_id'] in tasks;tasks[r['task_id']]['any10']|=r['kimi_k2_6_score']=='1' or r['kimi_k3_score']=='1'
 coverage={}
 for track in ['all','synthetic','expert']:
  group=[v for v in tasks.values() if track=='all' or v['track']==track];coverage[track]={'tasks':len(group),'at_least_one_of_eight_pass':sum(v['any8'] for v in group),'at_least_one_of_ten_pass':sum(v['any10'] for v in group)}
 result={'scope':'Existing stored scores; missing scores are end-to-end failures. No model or human regrading.','models':summaries,'thinking_pairs':pairs,'score_status_conflicts':issues,'observed_pass_coverage':coverage,'coverage_interpretation':'Automated-score coverage, not independently verified answerability.','rubric_interpretation':'Model-specific count-aligned records only; equal counts do not validate semantic alignment.'}
 (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 lines=['# Evaluation reconciliation','','The original overall rates match first-turn scores, not all 1,080 tasks.','Stored score reproduction below includes missing-score tasks as end-to-end failures.','','| Model | First-turn pass / 344 | First-turn % | All-task pass / 1,080 | All-task % |','|---|---:|---:|---:|---:|']
 for m in summaries:lines.append(f"| {m['model']} | {m['first_turn_passed']} | {m['first_turn_percent']:.2f} | {m['passed']} | {m['task_micro_percent']:.2f} |")
 lines+=['','## Thinking comparison','','Paired case-cluster bootstrap; 10,000 resamples, seed 23049.']
 for p in pairs:lines.append(f"- {p['thinking']} minus base: {p['difference_percentage_points']:.2f} percentage points, 95% interval [{p['case_cluster_bootstrap_95_percentage_points'][0]:.2f}, {p['case_cluster_bootstrap_95_percentage_points'][1]:.2f}].")
 lines+=['','## Data boundaries','','Ten rows have no valid stored score and are counted as failures.','One count-aligned Gemini-2.5-pro row has score 1 with a failed requirement; see summary.json.','Keeping stored scores gives 79/1,080 (7.31%); deterministic status normalization gives 78/1,080 (7.22%).','Neither policy is silently substituted for the historical scores.','Rubric summaries cover model-specific count-aligned subsets, not all criteria or an identical cross-model subset.','No human labels, judge-human agreement or independent answerability validation are inferred from these scores.']
 (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
 print('PASS: eight models, 8,640 rows, 344 cases, 1,080 tasks; wrote summary.json and SUMMARY.md.')

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,default=HERE);args=parser.parse_args();main(args.output_dir)
