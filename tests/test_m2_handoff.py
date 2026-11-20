import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_eval import contracts as c,service,review
from agent_eval.semantic import request,parse_response,SavedJudge
from agent_eval.reliability import reliability
from agent_eval.report import report
from agent_eval.store import Store
from examples.m2.create_handoff import make
from examples.m1.create_example import write


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.b,self.e,self.m,self.ref,self.tr=make(self.root)
        self.store=Store(self.root/'store')
        service.register_bundle(self.store,self.root/'bundle.json')
        service.register_experiment(self.store,self.root/'experiment.json')
        service.import_evidence(self.store,self.root/'evidence.json')

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def judge(self,verdicts=None,identity='fixture-judge'):
        responses={}
        for i,r in enumerate(self.store.all('run')):
            packet,_=request(self.store,r,self.b['tasks'][0],self.b['tasks'][0]['criteria'][0])
            verdict=(verdicts or ['met','unmet','met','unmet'])[i]
            responses[c.identity(packet)]=json.dumps({'verdict':verdict,'rationale':'PRIVATE_RATIONALE',
                'citations':[{'source':'output','quote':packet['sources']['output']}]},ensure_ascii=False)
        path=write(self.root,identity+'.json',{'schema_version':1,
            'evaluator':{'id':identity,'kind':'synthetic','version':'1','model':'fixture','settings':{}},'responses':responses})
        return SavedJudge(path)

    def human(self):
        # Simulates caller-attested provenance for contract tests; not validation evidence.
        self.ref['origin']='human';self.tr['origin']='human'
        review.reference_set(self.store,write(self.root,'ref.json',self.ref),True)
        review.task_review(self.store,write(self.root,'tr.json',self.tr),True)


class ContractTests(Fixture):
    def test_response_citations_and_schema(self):
        r=self.store.all('run')[0]
        packet,_=request(self.store,r,self.b['tasks'][0],self.b['tasks'][0]['criteria'][0])
        good={'verdict':'met','rationale':'evidence','citations':[{'source':'output','quote':packet['sources']['output']}]}
        self.assertEqual(parse_response(json.dumps(good),packet)['verdict'],'met')
        for mutation in ('quote','verdict','empty','extra'):
            bad=copy.deepcopy(good)
            if mutation=='quote':bad['citations'][0]['quote']='invented quote'
            if mutation=='verdict':bad['verdict']='success'
            if mutation=='empty':bad['citations']=[]
            if mutation=='extra':bad['confirmed']=True
            with self.subTest(mutation=mutation),self.assertRaises(c.ContractError):parse_response(json.dumps(bad),packet)

    def test_requests_never_include_reference_labels_or_private_files(self):
        r=self.store.all('run')[0];packet,_=request(self.store,r,self.b['tasks'][0],self.b['tasks'][0]['criteria'][0])
        self.assertNotIn('verdict',packet);self.assertNotIn('cases',packet);self.assertNotIn('PRIVATE_GRADING_CANARY',json.dumps(packet))
        public=service.execution_input(self.store,self.e['id'],'handoff')
        self.assertNotIn('rubric',public);self.assertNotIn('criteria',public)

    def test_reference_requires_attestation_and_exact_evidence(self):
        self.ref['origin']='human'
        with self.assertRaises(c.ContractError):review.reference_set(self.store,write(self.root,'ref.json',self.ref))
        self.ref['cases'][0]['output_sha256']='0'*64
        with self.assertRaises(c.ContractError):review.reference_set(self.store,write(self.root,'ref.json',self.ref),True)
        self.assertEqual(self.store.all('reference'),[])

    def test_task_review_versions_history_and_revocation(self):
        self.tr['origin']='human';p=write(self.root,'tr.json',self.tr)
        with self.assertRaises(c.ContractError):review.task_review(self.store,p)
        review.task_review(self.store,p,True);review.task_review(self.store,p,True)
        self.assertEqual(len(self.store.all('task_review')),1)
        changed={**self.tr,'id':'revoked','status':'rejected','supersedes':self.tr['id']}
        review.task_review(self.store,write(self.root,'revoked.json',changed),True)
        self.assertEqual(review.validity(self.store,self.e['bundle'],self.b['tasks'][0]),'rejected')
        stale={**self.tr,'id':'stale'}
        with self.assertRaises(c.ContractError):review.task_review(self.store,write(self.root,'stale.json',stale),True)
        self.assertEqual(len(self.store.all('task_review')),2)

    def test_reference_duplicates_and_immutable_version(self):
        review.reference_set(self.store,self.root/'reference.json')
        bad=copy.deepcopy(self.ref);bad['cases'][0]['verdict']='unmet'
        with self.assertRaises(c.ContractError):review.reference_set(self.store,write(self.root,'bad.json',bad))
        bad=copy.deepcopy(self.ref);bad['version']='2';bad['cases'].append({**bad['cases'][0],'id':'another'})
        with self.assertRaises(c.ContractError):review.reference_set(self.store,write(self.root,'bad.json',bad))

try:
    import inspect_ai
    INSPECT=True
except ImportError:INSPECT=False


@unittest.skipUnless(INSPECT,'optional Inspect adapter not installed')
class SemanticTests(Fixture):
    def evaluate(self,id='grade',verdicts=None):
        with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
            return service.evaluate(self.store,self.e['id'],id,'tester','test semantic evaluation',judge=self.judge(verdicts,id+'-judge'))

    def test_semantic_inspect_native_and_draft_preservation(self):
        first=self.evaluate();second=self.evaluate('again')
        self.assertTrue(all(j['processing']=='completed' for j in first['judgments']))
        self.assertTrue(all(j['confirmation']=='draft' for j in first['judgments']))
        for j in first['judgments']:self.assertTrue(self.store.read_blob(j['native_log_sha256']))
        self.assertEqual(self.store.get('evaluation','grade'),first)
        self.assertEqual(len(self.store.all('run')),4)
        self.assertEqual(reliability(self.store,'grade')['status'],'unverified')
        self.assertNotIn('PRIVATE_RATIONALE',json.dumps(report(self.store,self.e['id'],'grade')))

    def test_missing_evidence_avoids_judge(self):
        b=copy.deepcopy(self.b);b['id']='missing';b['tasks'][0]['inputs']=[]
        root=self.root/'missing';root.mkdir();
        for r in b['tasks'][0]['evaluation']:self.fail('unexpected private ref')
        service.register_bundle(self.store,write(root,'bundle.json',b))
        # Exercise adapter contract directly over immutable stored output.
        from agent_eval.semantic import evaluate
        r=self.store.all('run')[0]
        with patch.object(SavedJudge,'grade',side_effect=AssertionError('must not grade')):
            result,data=evaluate(self.store,r,b['tasks'][0],b['tasks'][0]['criteria'][0],self.judge())
        self.assertEqual(result['reason_code'],'missing_required_evidence');self.assertIsNone(data)

    def test_malformed_reply_is_error_and_raw_reply_retained(self):
        judge=self.judge();judge.responses={k:'not-json' for k in judge.responses}
        ev=service.evaluate(self.store,self.e['id'],'bad','tester','malformed',judge=judge)
        for j in ev['judgments']:
            self.assertEqual(j['processing'],'error');self.assertEqual(j['verdict'],'unknown')
            self.assertEqual(self.store.read_blob(j['response_sha256']),b'not-json')

    def test_reference_confusion_matrix_and_synthetic_unverified(self):
        self.evaluate(verdicts=['met','met','unmet','unmet'])
        review.reference_set(self.store,self.root/'reference.json')
        result=reliability(self.store,'grade','handoff-reference@1')
        self.assertEqual(result['synthetic_diagnostics']['confusion_matrix'],{'TP':1,'TN':1,'FP':1,'FN':1})
        self.assertEqual(result['synthetic_diagnostics']['agreement']['value'],0.5)
        self.assertEqual(result['synthetic_diagnostics']['false_positive_rate']['value'],0.5)
        self.assertEqual(result['synthetic_diagnostics']['false_negative_rate']['value'],0.5)
        self.assertEqual(result['status'],'unverified'); self.assertEqual(result['compared'],0)

    def test_unknown_na_errors_and_zero_denominator(self):
        self.evaluate(verdicts=['unknown','not_applicable','unknown','not_applicable'])
        self.human()
        result=reliability(self.store,'grade','handoff-reference@1')
        self.assertEqual(result['compared'],2);self.assertEqual(result['excluded']['unknown'],2)
        self.assertIsNone(result['false_positive_rate']['value'])
        judge=self.judge();judge.responses={k:'{}' for k in judge.responses}
        service.evaluate(self.store,self.e['id'],'bad','tester','errors',judge=judge)
        result=reliability(self.store,'bad','handoff-reference@1')
        self.assertEqual(result['excluded']['evaluation_error'],4);self.assertIsNone(result['agreement']['value'])

    def test_peer_disagreement_and_version_gate(self):
        self.evaluate();self.evaluate('other',['unmet']*4)
        result=reliability(self.store,'grade',peer_id='other')
        self.assertEqual(result['disagreement']['value'],0.5)
        ev=copy.deepcopy(self.store.get('evaluation','other'));ev['id']='different';ev['criterion_bundle']['version']='other'
        with self.store.db:self.store.put('evaluation','different',ev)
        with self.assertRaises(c.ContractError):reliability(self.store,'grade',peer_id='different')

    def test_review_changes_effective_result_not_original_and_validity_gates_success(self):
        ev=self.evaluate();self.human()
        j=ev['judgments'][0]
        audit={k:self.ref[k] for k in review.AUDIT}
        obj={'schema_version':1,'id':'review-1','evaluation':'grade','judgment':j['id'],
             'verdict':'met','supersedes':None,**audit}
        review.judgment_review(self.store,write(self.root,'j.json',obj),True)
        self.assertEqual(report(self.store,self.e['id'],'grade')['conditions'][0]['overall_confirmed_success_rate']['numerator'],1)
        revised={**obj,'id':'review-2','verdict':'unmet','supersedes':'review-1'}
        review.judgment_review(self.store,write(self.root,'j2.json',revised),True)
        self.assertEqual(report(self.store,self.e['id'],'grade')['conditions'][0]['overall_confirmed_success_rate']['numerator'],0)
        self.assertEqual(self.store.get('evaluation','grade'),ev)
        self.assertEqual(len(self.store.all('judgment_review')),2)


@unittest.skipUnless(INSPECT,'optional Inspect adapter not installed')
class ReportReviewTests(Fixture):
    def test_complete_review_and_revoked_validity(self):
        ev=service.evaluate(self.store,self.e['id'],'grade','tester','test',judge=self.judge())
        self.human()
        for index,j in enumerate(ev['judgments']):
            obj={'schema_version':1,'id':f'review-{index}','evaluation':'grade','judgment':j['id'],
                 'verdict':j['verdict'],'supersedes':None,**{k:self.ref[k] for k in review.AUDIT}}
            review.judgment_review(self.store,write(self.root,f'j{index}.json',obj),True)
        output=report(self.store,self.e['id'],'grade')
        self.assertEqual(output['confirmation'],'confirmed')
        self.assertEqual(output['conclusion'],'human_reviewed_results_on_approved_tasks')
        self.assertEqual(output['conditions'][0]['overall_confirmed_success_rate']['numerator'],2)
        revoked={**self.tr,'id':'revoked','status':'rejected','supersedes':self.tr['id']}
        review.task_review(self.store,write(self.root,'revoked.json',revoked),True)
        output=report(self.store,self.e['id'],'grade')
        self.assertEqual(output['conditions'][0]['overall_confirmed_success_rate']['numerator'],0)
        self.assertIn('withheld',output['conclusion'])
