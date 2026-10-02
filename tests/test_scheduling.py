import unittest
from datetime import datetime,timedelta
from aquaflow.lab.scheduling import Collector, Req, assign


def dt(h,m=0):return datetime(2026,10,2,h,m)


def people(spec):
    # spec: (name,certified,start hour,end hour)
    return [Collector(n,c,dt(sh),dt(eh)) for n,c,sh,eh in spec]


class SchedulingTests(unittest.TestCase):
    def test_back_to_back_jobs_share_collector(self):
        # A 30-minute job ending exactly when the next begins must be allowed
        # (half-open intervals) and land on the same collector.
        ps=people([("P",False,8,12)])
        rs=[
            Req("A",dt(8),dt(9),30,False),
            Req("B",dt(8),dt(9),30,False),
        ]
        got=assign(list(rs),ps)
        self.assertEqual(got["A"],("P",dt(8)))
        self.assertEqual(got["B"],("P",dt(8,30)))

    def test_shared_start_boundary_steps_at_five_minute_granularity(self):
        # Both requests can start 08:00; with one collector the second must
        # not double-book 08:00 but walk forward in 5-minute steps.
        ps=people([("P",False,8,12)])
        rs=[
            Req("A",dt(8),dt(9),30,False),
            Req("B",dt(8),dt(9),30,False),
        ]
        got=assign(list(rs),ps)
        self.assertEqual(got["A"],("P",dt(8)))
        self.assertEqual(got["B"],("P",dt(8,30)))
        # every candidate the search skipped on is a multiple of 5 minutes
        for _,start in got.values():
            self.assertEqual((start-dt(8)).seconds%(5*60),0)

    def test_actual_overlap_reschedules_onto_second_collector(self):
        # A second qualified collector appearing at the same boundary lets the
        # later (deterministically ordered) request keep its 08:00 start.
        rs=[
            Req("A",dt(8),dt(9),30,False),
            Req("B",dt(8),dt(9),30,False),
        ]
        one=assign(list(rs),people([("P",False,8,12)]))
        two=assign(list(rs),people([("P",False,8,12),("Q",False,8,12)]))
        self.assertEqual(one["A"],("P",dt(8)))
        self.assertEqual(one["B"],("P",dt(8,30)))
        self.assertEqual(two["A"],("P",dt(8)))
        self.assertEqual(two["B"],("Q",dt(8)))

    def test_assigned_intervals_never_overlap(self):
        ps=people([("P",False,8,12),("Q",False,8,12)])
        rs=[Req(c,dt(8),dt(10),20,False) for c in "ABCDEFGH"]
        got=assign(list(rs),ps)
        used={p.name:[] for p in ps}
        for site,(name,start) in got.items():
            used[name].append((start,start+timedelta(minutes=20)))
        for spans in used.values():
            spans.sort()
            for (s1,e1),(s2,e2) in zip(spans,spans[1:]):
                self.assertLessEqual(e1,s2)

    def test_certified_request_fails_without_certified_collector(self):
        ps=people([("P",False,8,12)])
        rs=[Req("A",dt(8),dt(9),30,True)]
        with self.assertRaises(ValueError) as cm:
            assign(rs,ps)
        self.assertIn("no available",str(cm.exception))
        self.assertIn("certified",str(cm.exception))

    def test_certified_request_fails_when_only_certified_collector_busy(self):
        ps=people([("P",False,8,12),("Q",True,8,12)])
        rs=[
            Req("A",dt(8),dt(9),60,True),
            Req("B",dt(8),dt(9),60,True),
        ]
        with self.assertRaises(ValueError):
            assign(rs,ps)

    def test_window_shorter_than_job_is_explicit_failure(self):
        ps=people([("P",False,8,12)])
        rs=[Req("A",dt(8),dt(8,10),30,False)]
        with self.assertRaises(ValueError):
            assign(rs,ps)

    def test_shift_boundaries_are_respected(self):
        ps=people([("P",False,8,11)])
        rs=[Req("A",dt(7),dt(12),30,False)]
        got=assign(rs,ps)
        # clamped to shift start, and the job still fits before shift end
        self.assertEqual(got["A"],("P",dt(8)))

    def test_deterministic_ordering_and_output(self):
        ps=people([("P",False,8,12),("Q",False,8,12)])
        rs=[
            Req("B",dt(8),dt(9),30,False),
            Req("A",dt(8),dt(9),30,False),
        ]
        first=assign(list(rs),ps)
        second=assign(list(reversed(rs)),ps)
        self.assertEqual(first,second)
        self.assertEqual(first["A"],("P",dt(8)))
        self.assertEqual(first["B"],("Q",dt(8)))


class WorkflowTests(unittest.TestCase):
    def _payload(self,cert_request=False,cert_collector=True):
        return {
            "requests":[
                {"site":"A","earliest":"2026-10-02T08:00","latest":"2026-10-02T09:00","minutes":30,"certified":False},
                {"site":"B","earliest":"2026-10-02T08:00","latest":"2026-10-02T09:00","minutes":30,"certified":cert_request},
            ],
            "collectors":[
                {"name":"P","certified":False,"start":"2026-10-02T08:00","end":"2026-10-02T12:00"},
                {"name":"Q","certified":cert_collector,"start":"2026-10-02T08:00","end":"2026-10-02T12:00"},
            ],
        }

    def test_workflow_exclusive_occupancy(self):
        from aquaflow.workflow_rules import evaluate
        r=evaluate("collector_schedule",self._payload())
        self.assertEqual(r["value"]["A"][0],"P")
        self.assertEqual(r["value"]["B"][0],"Q")
        self.assertEqual(r["value"]["A"][1],"2026-10-02T08:00:00")

    def test_workflow_certification_failure_is_explicit(self):
        from aquaflow.workflow_rules import evaluate
        payload=self._payload(cert_request=True,cert_collector=False)
        with self.assertRaises(ValueError):
            evaluate("collector_schedule",payload)

    def test_normalized_contract_is_v1(self):
        from aquaflow.workflow_models import normalize
        env=normalize("collector_schedule",self._payload(cert_request=True))
        self.assertEqual(env.payload["_contract"],"v1")
        self.assertNotIn("_occupancy_guard",env.payload)
        self.assertTrue(env.payload["requests"][1]["certified"])


if __name__=="__main__":
    unittest.main()
