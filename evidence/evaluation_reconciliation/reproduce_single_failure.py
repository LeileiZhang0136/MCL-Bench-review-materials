"""Locate existing automated single-requirement failures; do not create human labels."""
import argparse,csv,json
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main(out):
 out.mkdir(parents=True,exist_ok=True);records=[]
 for r in csv.DictReader((HERE/'main_model_task_scores.csv').open()):
  st=json.loads(r['requirement_status_json']);nr=int(r['rubric_entry_count'])
  if nr and len(st)==nr and int(r['effective_score'])==0 and st.count('yes')==nr-1:
   failed=next(i for i,s in enumerate(st,1) if s!='yes')
   records.append({'task_id':r['task_id'],'case_id':r['case_id'],'inference_model':r['model'],'source_track':r['source_track'],'category':r['category'],'subcategory':r['subcategory'],'rubric_entry_count':nr,'failed_entry_index_1based':failed,'stored_failed_status':st[failed-1],'effective_score':0})
 records.sort(key=lambda r:(r['case_id'],r['task_id'],r['inference_model']))
 counts=Counter(r['inference_model'] for r in records)
 reference=json.loads((HERE/'summary.json').read_text())
 assert counts=={r['model']:r['aligned_single_failure_tasks'] for r in reference['models']}
 with (out/'single_failure_records.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
 predictions={};judgments={};tasks={}
 for filename,target in [('predictions.jsonl',predictions),('judgments_gpt5.2.jsonl',judgments)]:
  for line in (ROOT/'evaluation/released_examples'/filename).read_text().splitlines():
   d=json.loads(line);target[(d['task_id'].replace('_T','/T'),d['inference_model'])]=d
 for p in (ROOT/'examples').glob('**/case.json'):
  case=p.parent.name.split('_')[0]
  for i,t in enumerate(json.loads(p.read_text()),1):tasks[f'{case}/T{i}']=(t,p.relative_to(ROOT).as_posix())
 examples=[];used=set()
 for r in records:
  model=r['inference_model'];key=(r['task_id'],model)
  if model in used or key not in predictions or key not in judgments:continue
  t,path=tasks[r['task_id']];j=judgments[key];st=j.get('requirement_status',[]);rubrics=t.get('rubrics',[]);nr=r['rubric_entry_count']
  if j.get('score')!=0 or len(st)!=nr or len(rubrics)!=nr or st.count('yes')!=nr-1:continue
  idx=r['failed_entry_index_1based']
  if st[idx-1]=='yes':continue
  examples.append({**r,'public_case_path':path,'rubrics':rubrics,'requirement_status':st,'failed_rubric':rubrics[idx-1],'model_output':predictions[key]['model_output'],'grading_rationale':j['grading_rationale'],'annotation_status':'Existing automated record; not a human correctness label or an assertion that this failure is justified.'});used.add(model)
 (out/'single_failure_examples.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in examples)+'\n')
 lines=['# Inspecting single-requirement failures','','## Located records','',f'The count-aligned existing-score records contain {len(records)} failed task-model responses with exactly one non-yes status. These are response records, not distinct tasks or human-labeled errors.','','| Inference model | Records |','|---|---:|']
 for model,n in sorted(counts.items()):lines.append(f'| {model} | {n} |')
 lines+=['','[Complete record index](single_failure_records.csv) identifies the anonymous task, model and failed serialized-entry position.','[Illustrative responses](single_failure_examples.jsonl) include the full released response, rubric list, statuses and grading rationale.','Examples are selected as the first eligible public record per inference model in the index order.','They must have a failing public judgment, equal rubric/status counts and the indexed single failure.','This is an inspectable panel, not a statistical or human-validity sample.','','## What to inspect','','- Does the failed item express an explicit task requirement?','- Does the rationale identify a substantive rule, evidence or state-update violation?','- Does it instead penalize a meaning-preserving paraphrase, an undeclared formatting restriction or harmless background explanation?','- Are the serialized entry and the intended logical criterion actually aligned? Equal list lengths alone do not establish this.','','## Relationship to existing author review','','The [historical targeted author-review account](../judge_calibration/README.md#historical-targeted-author-review-account) reports 100 reviewed responses.','The new record index is not that historical review set. No human labels, judge-human agreement, or correctness decisions are inferred for the indexed responses.','The separate three-judge comparison is also not a substitute for human agreement.','These materials expose boundary cases for inspection without claiming that a single failed item is automatically a genuine error or an automatic misjudgment.','','## Reproduce','','```bash','python evidence/evaluation_reconciliation/reproduce_single_failure.py --output-dir reproduced/single_failure','```']
 (out/'SINGLE_FAILURE_REVIEW.md').write_text('\n'.join(lines)+'\n')
 print(f'PASS: {len(records)} existing single-failure records; {len(examples)} inspectable examples; model counts match the reconciliation.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=HERE);main(p.parse_args().output_dir)
