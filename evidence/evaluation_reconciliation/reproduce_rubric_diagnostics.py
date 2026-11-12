"""Reproduce rubric diagnostics directly from anonymous task-model records."""
import argparse,csv,json
from pathlib import Path
from collections import defaultdict
HERE=Path(__file__).resolve().parent

def main(out):
 out.mkdir(parents=True,exist_ok=True)
 groups=defaultdict(list)
 for r in csv.DictReader((HERE/'main_model_task_scores.csv').open()):groups[r['model']].append(r)
 metrics=[];strata=[]
 for model,rows in groups.items():
  assert len(rows)==1080
  aligned=[]
  for r in rows:
   status=json.loads(r['requirement_status_json']);nr=int(r['rubric_entry_count'])
   if nr and len(status)==nr:aligned.append((r,status,nr))
  yes=sum(s.count('yes') for _,s,_ in aligned);total=sum(n for _,_,n in aligned)
  metrics.append({'model':model,'count_aligned_tasks':len(aligned),'excluded_tasks':1080-len(aligned),'satisfied_entries':yes,'eligible_entries':total,'satisfaction_percent':100*yes/total,'failed_tasks_with_one_unsatisfied_entry':sum(int(r['effective_score'])==0 and n-s.count('yes')==1 for r,s,n in aligned)})
  for lo,hi,label in [(1,4,'1-4'),(5,8,'5-8'),(9,12,'9-12'),(13,100000,'13+')]:
   rr=[r for r in rows if lo<=int(r['rubric_entry_count'])<=hi];passed=sum(int(r['effective_score']) for r in rr)
   strata.append({'model':model,'rubric_count_bucket':label,'passed_tasks':passed,'tasks':len(rr),'success_percent':100*passed/len(rr) if rr else None})
 # Cross-check independently derived counts against the existing reconciliation.
 ref={m['model']:m for m in json.loads((HERE/'summary.json').read_text())['models']}
 for m in metrics:
  r=ref[m['model']];assert m['satisfied_entries']==r['aligned_rubrics_yes'] and m['eligible_entries']==r['aligned_rubrics_total'] and m['count_aligned_tasks']==r['count_aligned_tasks'] and m['failed_tasks_with_one_unsatisfied_entry']==r['aligned_single_failure_tasks']
 for s in strata:
  r=ref[s['model']]['rubric_count_buckets'][s['rubric_count_bucket']];assert s['tasks']==r['tasks'] and s['passed_tasks']==r['passed']
 for name,rows in [('rubric_satisfaction.csv',metrics),('success_by_rubric_count.csv',strata)]:
  with (out/name).open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 lines=['# Rubric-level and rubric-count diagnostics','','## Rubric satisfaction','','This table includes nonempty records with equal serialized rubric and status counts.','Coverage is model-specific; it is not an identical shared subset or a ranking.','','| Model | Eligible tasks | Satisfied / eligible entries | Satisfaction | Single-entry failed tasks |','|---|---:|---:|---:|---:|']
 for m in metrics:lines.append(f"| {m['model']} | {m['count_aligned_tasks']} | {m['satisfied_entries']}/{m['eligible_entries']} | {m['satisfaction_percent']:.2f}% | {m['failed_tasks_with_one_unsatisfied_entry']} |")
 lines+=['','## Task success by serialized rubric count','','All 1,080 tasks per model enter this breakdown. Counts are serialized entries,','not an independently reconciled number of logical criteria.','','| Model | Entries per task | Passed / tasks | Success |','|---|---|---:|---:|']
 for s in strata:lines.append(f"| {s['model']} | {s['rubric_count_bucket']} | {s['passed_tasks']}/{s['tasks']} | {s['success_percent']:.2f}% |")
 lines+=['','## Definitions and scope','','- Satisfaction is yes statuses divided by entries in count-aligned records, pooled within each model.','- Equal counts are a structural screen and do not certify semantic alignment or correct judgments.','- Single-entry failed tasks have effective score zero and exactly one non-yes status in the eligible subset. This is not a human error label.','- Count-stratified success is successful tasks divided by all tasks in that bucket. Missing scores remain end-to-end failures, consistently with the score export.','- Stored-score and status-normalized results differ for one Gemini-2.5-pro task; the stored-score policy is used here and the reconciliation documents its sensitivity.','- Rubric count is associated with task family and difficulty; these strata do not identify a causal effect of requirement count.','- These are existing-record diagnostics, not new model calls or human evaluations.','','## Reproduce','','```bash','python evidence/evaluation_reconciliation/reproduce_rubric_diagnostics.py --output-dir reproduced/rubric_diagnostics','```']
 (out/'RUBRIC_DIAGNOSTICS.md').write_text('\n'.join(lines)+'\n')
 print('PASS: 8 model summaries and 32 rubric-count strata reproduced and cross-checked.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=HERE);main(p.parse_args().output_dir)
