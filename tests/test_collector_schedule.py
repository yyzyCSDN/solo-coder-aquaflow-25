import unittest
from datetime import datetime,timedelta
from aquaflow.api import AquaFlowService
from aquaflow.lab.scheduling import Collector,Req,assign
from aquaflow.workflow_rules import evaluate

D=datetime(2026,10,2,9,0)
def req(site,eh,em,lh,lm,minutes,certified=False):
    return Req(site,D.replace(hour=eh,minute=em),D.replace(hour=lh,minute=lm),minutes,certified)
def person(name,certified,sh=8,sm=0,eh=17,em=0):
    return Collector(name,certified,D.replace(hour=sh,minute=sm),D.replace(hour=eh,minute=em))
def span(assigned,site,minutes):
    name,start=assigned[site];return name,start,start+timedelta(minutes=minutes)

class SchedulingTest(unittest.TestCase):
    def test_back_to_back_allowed(self):
        # 首尾相接: second request starts exactly when the first ends -> same collector, no gap
        reqs=[req("A",9,0,10,0,30),req("B",9,30,10,30,30)]
        out=assign(reqs,[person("c1",True)])
        self.assertEqual(span(out,"A",30),("c1",D,D.replace(hour=9,minute=30)))
        self.assertEqual(span(out,"B",30),("c1",D.replace(hour=9,minute=30),D.replace(hour=10,minute=0)))
    def test_overlap_pushed_to_free_slot(self):
        # 实际重叠: shared start boundary, one collector -> second request moves to first free slot
        reqs=[req("A",9,0,12,0,30),req("B",9,0,12,0,30)]
        out=assign(reqs,[person("c1",True)])
        _,a0,a1=span(out,"A",30);_,b0,b1=span(out,"B",30)
        self.assertTrue(a1<=b0 or b1<=a0)
        self.assertEqual(a0,D);self.assertEqual(b0,D.replace(hour=9,minute=30))
    def test_second_collector_absorbs_conflict(self):
        # 第二名采样人员出现时, conflicting request is rescheduled onto them at 09:00
        reqs=[req("A",9,0,12,0,30),req("B",9,0,12,0,30)]
        out=assign(reqs,[person("c1",True),person("c2",True)])
        self.assertEqual(out["A"],("c1",D))
        self.assertEqual(out["B"],("c2",D))
    def test_deterministic_ordering(self):
        reqs=[req("B",9,0,12,0,30),req("A",9,0,10,0,30)]
        people=[person("c1",True),person("c2",True)]
        self.assertEqual(assign(reqs,people),assign(list(reversed(reqs)),people))
        self.assertEqual(assign(reqs,people),assign(reqs,people))
    def test_certified_request_requires_certified_collector(self):
        out=assign([req("A",9,0,12,0,30,True)],[person("c1",False),person("c2",True)])
        self.assertEqual(out["A"][0],"c2")
    def test_unschedulable_certified_request_fails(self):
        # 完全不可排班: certified request, no certified collector -> explicit failure
        with self.assertRaises(ValueError):
            assign([req("A",9,0,12,0,30,True)],[person("c1",False)])
    def test_unschedulable_window_fails(self):
        # 完全不可排班: job longer than the feasible window inside the shift
        with self.assertRaises(ValueError):
            assign([req("A",9,0,9,30,45)],[person("c1",True)])
        # fully booked collector, tight windows leave no free slot
        with self.assertRaises(ValueError):
            assign([req("A",9,0,9,30,30),req("B",9,0,9,30,30)],[person("c1",True)])

class WorkflowTest(unittest.TestCase):
    def payload(self,requests,collectors):
        return {"requests":requests,"collectors":collectors}
    def test_workflow_no_overlap_and_audit(self):
        p=self.payload(
            [{"site":"A","earliest":"2026-10-02T09:00:00","latest":"2026-10-02T12:00:00","minutes":30,"certified":False},
             {"site":"B","earliest":"2026-10-02T09:00:00","latest":"2026-10-02T12:00:00","minutes":30,"certified":False}],
            [{"name":"c1","certified":True,"start":"2026-10-02T08:00:00","end":"2026-10-02T17:00:00"},
             {"name":"c2","certified":True,"start":"2026-10-02T08:00:00","end":"2026-10-02T17:00:00"}])
        r=AquaFlowService().run_workflow("collector_schedule",p)
        self.assertEqual(r["decision"],"schedule")
        self.assertEqual(r["value"],{"A":["c1","2026-10-02T09:00:00"],"B":["c2","2026-10-02T09:00:00"]})
        self.assertEqual(r["audit"]["contract"],"v1")
    def test_workflow_unschedulable_certified_fails(self):
        p=self.payload(
            [{"site":"A","earliest":"2026-10-02T09:00:00","latest":"2026-10-02T12:00:00","minutes":30,"certified":True}],
            [{"name":"c1","certified":False,"start":"2026-10-02T08:00:00","end":"2026-10-02T17:00:00"}])
        with self.assertRaises(ValueError):
            AquaFlowService().run_workflow("collector_schedule",p)
        with self.assertRaises(ValueError):
            evaluate("collector_schedule",p)

if __name__=="__main__":unittest.main()
