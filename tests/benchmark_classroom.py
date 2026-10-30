"""Disposable loopback benchmark; never reads or changes classroom records."""
import argparse
import copy
import hashlib
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_learning as fixtures
from app import learning, storage
from app.security import new_session


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--students',type=int,default=30);args=parser.parse_args()
    fixture=fixtures.LearningTests();fixture.setUp()
    try:
        ids=[f'LOAD{i:03}' for i in range(args.students)]
        students=storage.read_json('students.json');base=students['s1']
        for sid in ids:
            students[sid]={**base,'student_id':sid,'full_name':sid}
            fixture.tokens[sid]=new_session(sid,'student','127.0.0.1','benchmark')
        storage.write_json('students.json',students)
        course=fixture.course(','.join(ids))
        tasks=[fixture.create('assignment',course_id=course,title=f'Task {i}',due_at=fixture.future,max_attempts='20') for i in range(10)]
        data=learning.load();learning.FILES.mkdir(parents=True,exist_ok=True);(learning.FILES/'benchmark.txt').write_bytes(b'answer')
        for sid in ids:
            for task in tasks:
                for attempt in range(3):data['submissions'].append({'id':f'{sid}-{task}-{attempt}','assignment_id':task,'course_id':course,'student_id':sid,'assignment_title':'Task','score':10,'original_filename':'answer.txt','stored_name':'benchmark.txt','attempt':attempt+1,'created_at':storage.utc_now(),'size_bytes':6,'sha256':hashlib.sha256(b'answer').hexdigest()})
        storage.write_json('learning.json',data)
        report={'students':len(ids),'historical_submissions':len(data['submissions']),'transport':'loopback; disposable data; Docker idle','phases':{}}
        for name in ('workspace','submit'):
            def call(sid):
                started=time.perf_counter()
                if name=='workspace':code,result=fixture.request('/api/student/workspace',sid)
                else:code,result=fixture.request('/api/learning/submit',sid,{'assignment_id':tasks[0],'request_id':'load-'+sid},file=('answer.txt',b'new answer'))
                return code,1000*(time.perf_counter()-started)
            with ThreadPoolExecutor(max_workers=len(ids)) as pool:results=list(pool.map(call,ids))
            latency=sorted(row[1] for row in results)
            report['phases'][name]={'requests':len(results),'errors':sum(code!=200 for code,_ in results),'median_ms':round(statistics.median(latency),1),'p95_ms':round(latency[min(len(latency)-1,int(.95*len(latency)))],1),'max_ms':round(max(latency),1)}
        final=learning.load()['submissions'];report['new_receipts']=len(final)-len(data['submissions'])
        assert report['new_receipts']==len(ids),report
        assert all(phase['errors']==0 for phase in report['phases'].values()),report
        target=Path(__file__).resolve().parents[1]/'logs'/'backend-load.json';target.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally:fixture.doCleanups()


if __name__=='__main__':main()
