"""
Reference execution of the workload on any model variant.

Each function below executes one query of repo/queries.txt (Model B) or
repo/supplementary/queries_baseline.txt (Model A) on the in-memory replica,
following the pattern order written in the Cypher text: anchor on the label
or index given first, then expand along the pattern. Every node scanned or
sought, relationship expanded, property read and string-to-value conversion
is counted, so the cost of the SAME logical query can be compared across
model variants without any engine-specific caching or planner effects.

The functions branch on g.flags only where the graph structure differs:
  labels       role / subtype on the same node        vs  IS_A hop
  fold         [:TOOK] relationship with result props vs  SubjectEnrolment + Result nodes
  pivot        phone_mobile/home/work properties      vs  PhoneNumber nodes
  materialise  Invoice.balance_owing                  vs  sum of lines minus payments
  next_term    [:NEXT_TERM] hop                       vs  scan and sort Term nodes
  typed        stored date / float values             vs  date() / toFloat() at query time
"""
import datetime
from collections import defaultdict

AS_AT = datetime.date(2026, 9, 14)
PASS = ('A', 'B', 'C')


class Meter:
    def __init__(self, g):
        self.g = g
        self.f = g.flags
        self.reset()

    def reset(self):
        self.scanned = 0        # nodes produced by label scans
        self.seeks = 0          # index seeks
        self.expansions = 0     # relationships traversed
        self.reads = 0          # property reads (node or relationship)
        self.conversions = 0    # date()/toFloat() calls on string values
        self.touched = set()    # distinct nodes touched

    def cost(self):
        return dict(scanned=self.scanned, seeks=self.seeks, expansions=self.expansions,
                    reads=self.reads, conversions=self.conversions, touched=len(self.touched),
                    accesses=self.scanned + self.seeks + self.expansions + self.reads)

    # ---- primitive operations ---------------------------------------------------------
    def scan(self, label):
        res = [n for n, v in self.g.nodes.items() if label in v['labels']]
        self.scanned += len(res)
        self.touched.update(res)
        return res

    def seek(self, label, **key):
        self.seeks += 1
        n = self.g.find(label, **key)
        if n:
            self.touched.add(n)
        return n

    def seek_prop(self, label, prop, value):
        """Unique-index seek on a non-key property (constraint-backed in both models)."""
        self.seeks += 1
        for n, v in self.g.nodes.items():
            if label in v['labels'] and v['props'].get(prop) == value:
                self.touched.add(n)
                return n
        return None

    def exp(self, n, typ, direction='out'):
        if n is None:
            return []
        adj = self.g.out if direction == 'out' else self.g.inn
        res = []
        for rid in adj[n][typ]:
            self.expansions += 1
            r = self.g.rels[rid]
            other = r['end'] if direction == 'out' else r['start']
            self.touched.add(other)
            res.append((r, other))
        return res

    def p(self, n, key):
        if n is None:
            return None
        self.reads += 1
        return self.g.nodes[n]['props'].get(key)

    def rp(self, r, key):
        self.reads += 1
        return r['props'].get(key)

    def has(self, n, label):
        return n is not None and label in self.g.nodes[n]['labels']

    def date(self, v):
        if v is None or isinstance(v, datetime.date):
            return v
        self.conversions += 1
        return datetime.date.fromisoformat(v)

    def num(self, v):
        if v is None or isinstance(v, float):
            return v
        self.conversions += 1
        return float(v)

    # ---- model-dependent navigation -------------------------------------------------------
    def person(self, role_node):
        """Node that carries PERSON attributes for a Student/Staff/Guardian node."""
        if self.f['labels']:
            return role_node
        ups = self.exp(role_node, 'IS_A', 'out')
        return ups[0][1] if ups else None

    def role_of(self, person_node, label):
        """Role node of a person (labels: same node if it carries the label)."""
        if self.f['labels']:
            return person_node if self.has(person_node, label) else None
        for _, n in self.exp(person_node, 'IS_A', 'in'):
            if self.has(n, label):
                return n
        return None

    def took_out(self, student):
        """(record, offering) pairs; record = TOOK relationship or SubjectEnrolment node."""
        if self.f['fold']:
            return [(('rel', r), o) for r, o in self.exp(student, 'TOOK', 'out')]
        res = []
        for _, se in self.exp(student, 'HAS_SUBJECT_ENROLMENT', 'out'):
            for _, o in self.exp(se, 'FOR_OFFERING', 'out'):
                res.append((('node', se), o))
        return res

    def took_in(self, offering):
        if self.f['fold']:
            return [(('rel', r), s) for r, s in self.exp(offering, 'TOOK', 'in')]
        res = []
        for _, se in self.exp(offering, 'FOR_OFFERING', 'in'):
            for _, s in self.exp(se, 'HAS_SUBJECT_ENROLMENT', 'in'):
                res.append((('node', se), s))
        return res

    def status(self, rec):
        kind, x = rec
        return self.rp(x, 'status') if kind == 'rel' else self.p(x, 'se_status')

    def result(self, rec, key):
        """Read one result attribute (None if no result)."""
        kind, x = rec
        if kind == 'rel':
            return self.rp(x, key)
        res = self.exp(x, 'HAS_RESULT', 'out')
        return self.p(res[0][1], key) if res else None

    def has_result(self, rec):
        kind, x = rec
        if kind == 'rel':
            return self.rp(x, 'result_type') is not None
        return len(self.exp(x, 'HAS_RESULT', 'out')) > 0

    def balance(self, inv):
        if self.f['materialise']:
            return self.p(inv, 'balance_owing')
        total = sum(self.num(self.p(l, 'line_amount')) for _, l in self.exp(inv, 'HAS_LINE', 'out'))
        paid = sum(self.num(self.p(pm, 'amount_paid')) for _, pm in self.exp(inv, 'SETTLES', 'in'))
        return total - paid

    def totals(self, inv):
        if self.f['materialise']:
            return self.p(inv, 'total_amount'), self.p(inv, 'amount_paid'), self.p(inv, 'balance_owing')
        total = sum(self.num(self.p(l, 'line_amount')) for _, l in self.exp(inv, 'HAS_LINE', 'out'))
        paid = sum(self.num(self.p(pm, 'amount_paid')) for _, pm in self.exp(inv, 'SETTLES', 'in'))
        return total, paid, total - paid

    def next_term(self, cur):
        if self.f['next_term']:
            nx = self.exp(cur, 'NEXT_TERM', 'out')
            return nx[0][1] if nx else None
        cur_end = self.date(self.p(cur, 'end_date'))
        cands = [(self.date(self.p(t, 'start_date')), t) for t in self.scan('Term')]
        cands = [c for c in cands if c[0] > cur_end]
        return min(cands)[1] if cands else None

    def phone(self, person, ptype):
        if self.f['pivot']:
            return self.p(person, 'phone_' + ptype.lower())
        for _, ph in self.exp(person, 'HAS_PHONE', 'out'):
            if self.p(ph, 'phone_type') == ptype:
                return self.p(ph, 'phone_number')
        return None

    def name(self, person):
        return f"{self.p(person, 'preferred_name')} {self.p(person, 'family_name')}"


# =============================================================================
# The six workload queries
# =============================================================================
def q1_conflict(m):
    out = []
    for st in m.scan('Staff'):
        # (p:Staff&Guardian)  |  (st:Staff)-[:IS_A]->(sp:Person)<-[:IS_A]-(gd:Guardian)
        sp = m.person(st)
        gd = m.role_of(sp, 'Guardian')
        if gd is None:
            continue
        for grel, child in m.exp(gd, 'GUARDIAN_OF', 'out'):
            cp = m.person(child)
            matches = []
            for rec, o in m.took_out(child):
                if any(lead == st for _, lead in m.exp(o, 'LEADS', 'in')):
                    subj = m.exp(o, 'OF_SUBJECT', 'out')[0][1]
                    term = m.exp(o, 'IN_TERM', 'out')[0][1]
                    matches.append((rec, o, subj, term))
            for rec, o, subj, term in (matches or [(None, None, None, None)]):
                if o is None:
                    action = None
                elif not m.has_result(rec):
                    action = 'Not yet assessed - reassign assessor now'
                else:
                    action = 'Result awarded ' + str(m.result(rec, 'awarded_date')) + ' - independent re-mark'
                eligible = []
                if subj is not None:
                    for _, off in m.exp(subj, 'OF_SUBJECT', 'in'):
                        for _, alt in m.exp(off, 'LEADS', 'in'):
                            if alt == st:
                                continue
                            ap = m.person(alt)
                            # NOT EXISTS { (alt)-[:GUARDIAN_OF]->(child) }
                            ag = m.role_of(ap, 'Guardian') if not m.f['labels'] else alt
                            if any(c == child for _, c in m.exp(ag, 'GUARDIAN_OF', 'out')):
                                continue
                            if not (m.date(m.p(alt, 'blue_card_expiry')) >= m.date(m.p(term, 'end_date'))):
                                continue
                            nm = m.name(ap)
                            if nm not in eligible:
                                eligible.append(nm)
                out.append(dict(
                    staff_member=m.name(sp), position=m.p(st, 'position_title'),
                    dependant=m.name(cp), relationship=m.rp(grel, 'relationship_type'),
                    finding='No conflict' if o is None else 'CONFLICT',
                    subject=None if subj is None else f"{m.p(subj, 'subject_code')} {m.p(subj, 'subject_title')}",
                    campus=m.p(o, 'campus_code'), term=m.p(term, 'term_code'),
                    action=action, eligible_assessors=eligible))
    return sorted(out, key=lambda r: (r['finding'], r['staff_member']))


def q2_bluecard(m):
    cur = None
    for t in m.scan('Term'):
        if m.date(m.p(t, 'start_date')) <= AS_AT <= m.date(m.p(t, 'end_date')):
            cur = t
    nxt = m.next_term(cur)
    out = []
    for s in m.scan('Staff'):
        expiry = m.date(m.p(s, 'blue_card_expiry'))
        if not expiry <= m.date(m.p(nxt, 'end_date')):
            continue
        # chain = (top)-[:SUPERVISES*0..]->(s), expanded upwards from the bound end s
        path, node = [s], s
        while True:
            ups = m.exp(node, 'SUPERVISES', 'in')        # also the NOT EXISTS test on each candidate top
            if not ups:
                break
            node = ups[0][1]
            path.append(node)
        upward = path                                     # s, manager, ..., root
        rostered, students = [], []
        for _, o in m.exp(s, 'LEADS', 'out'):
            if any(t == nxt for _, t in m.exp(o, 'IN_TERM', 'out')):
                rostered.append(f"{m.p(o, 'subject_code')}@{m.p(o, 'campus_code')}")
        for _, o in m.exp(s, 'LEADS', 'out'):
            if any(t == nxt for _, t in m.exp(o, 'IN_TERM', 'out')):
                for rec, st in m.took_in(o):
                    if m.status(rec) == 'ENROLLED':
                        pid = m.p(st, 'person_id')
                        if pid not in students:
                            students.append(pid)
        if not rostered:
            risk = 'RENEW - not rostered in ' + m.p(nxt, 'term_code')
        elif expiry < m.date(m.p(nxt, 'start_date')):
            risk = 'BLOCKER - lapses before ' + m.p(nxt, 'term_code') + ' starts'
        else:
            risk = 'BLOCKER - lapses during ' + m.p(nxt, 'term_code')
        people = [m.person(x) for x in upward]
        chain_text = ' > '.join(m.p(x, 'preferred_name') for x in people)
        mgr = people[1] if len(people) > 1 else None
        contact = (m.phone(mgr, 'MOBILE') or m.phone(mgr, 'WORK') or m.p(mgr, 'email')) if mgr else None
        out.append(dict(staff_member=m.name(people[0]), position=m.p(s, 'position_title'),
                        blue_card_expiry=expiry.isoformat(), days_remaining=(expiry - AS_AT).days,
                        risk=risk, offerings_next_term=rostered, students_affected=len(students),
                        escalation_chain=chain_text, manager_contact=contact))
    return sorted(out, key=lambda r: (r['risk'], r['days_remaining']))


def q3_debt(m):
    rows = []
    for c in m.scan('Campus'):
        open_inv, debtors = [], set()
        for _, e in m.exp(c, 'AT_CAMPUS', 'in'):
            if not m.has(e, 'Enrolment') or m.p(e, 'enrolment_status') != 'ACTIVE':
                continue
            for _, s in m.exp(e, 'HAS_ENROLMENT', 'in'):
                for _, i in m.exp(s, 'RAISED_FOR', 'in'):
                    bal = m.balance(i)
                    if bal > 0:
                        open_inv.append((i, bal))
                        debtors.add(s)
        # reduce() passes: B re-reads balance_owing / due_date; A reuses the computed map values
        debt = aged = 0.0
        for i, bal in open_inv:
            b = m.p(i, 'balance_owing') if m.f['materialise'] else bal
            debt += b
        for i, bal in open_inv:
            due = m.date(m.p(i, 'due_date'))
            b = m.p(i, 'balance_owing') if m.f['materialise'] else bal
            aged += b if (AS_AT - due).days > 90 else 0.0
        rows.append(dict(campus=m.p(c, 'campus_name'), invoices=len(open_inv), debtors=len(debtors),
                         debt=debt, aged=aged))
    avg = sum(r['debt'] for r in rows) / len(rows)
    out = [dict(campus=r['campus'], open_invoices=r['invoices'], debtor_students=r['debtors'],
                balance_owing=round(r['debt'], 2), variance_vs_average=round(r['debt'] - avg, 2),
                pct_over_90_days=0.0 if r['debt'] == 0 else round(100.0 * r['aged'] / r['debt'], 1),
                flag='ABOVE AVERAGE - escalate' if r['debt'] > avg else 'within average',
                school_average=round(avg, 2)) for r in rows]
    return sorted(out, key=lambda r: -r['balance_owing'])


def q4_prereq(m):
    found = []
    seen = set()
    for s in m.scan('Student'):
        for rec, o in m.took_out(s):
            if m.status(rec) == 'WITHDRAWN':
                continue
            subj = m.exp(o, 'OF_SUBJECT', 'out')[0][1]
            term = m.exp(o, 'IN_TERM', 'out')[0][1]
            # (subj)-[:REQUIRES]->+(pre): breadth-first transitive closure
            pres, frontier = [], [subj]
            while frontier:
                nxt = []
                for x in frontier:
                    for _, y in m.exp(x, 'REQUIRES', 'out'):
                        if y not in pres:
                            pres.append(y)
                            nxt.append(y)
                frontier = nxt
            for pre in pres:
                key = (s, rec[1] if rec[0] == 'node' else id(rec[1]), subj, term, pre)
                if key in seen:
                    continue
                seen.add(key)
                attempts = []
                for rec2, o2 in m.took_out(s):
                    if any(x == pre for _, x in m.exp(o2, 'OF_SUBJECT', 'out')):
                        start = m.date(m.p(m.exp(o2, 'IN_TERM', 'out')[0][1], 'start_date'))
                        outcome = (m.result(rec2, 'grade_letter') or m.result(rec2, 'competency_outcome')
                                   or m.status(rec2))
                        attempts.append(dict(term=m.p(o2, 'term_code'), start=start, outcome=outcome))
                t_start = m.date(m.p(term, 'start_date'))
                if any(a['start'] < t_start and a['outcome'] in PASS for a in attempts):
                    continue
                found.append((s, rec, subj, term, pre, attempts))
    out = []
    for s, rec, subj, term, pre, attempts in found:
        prog = None
        for _, e in m.exp(s, 'HAS_ENROLMENT', 'out'):
            if m.p(e, 'enrolment_status') == 'ACTIVE':
                prog = m.exp(e, 'IN_PROGRAM', 'out')[0][1]
        incl = [x for _, x in m.exp(prog, 'INCLUDES', 'out')] if prog else []
        if prog is None:
            cause = 'No active enrolment'
        elif subj not in incl:
            cause = 'Enrolled outside program'
        elif pre not in [x for _, x in m.exp(prog, 'INCLUDES', 'out')]:
            cause = 'Program design gap'
        else:
            cause = 'Progression control failure'
        sp = m.person(s)
        out.append(dict(student_no=m.p(s, 'student_no'), student=m.name(sp),
                        program=m.p(prog, 'program_code'), subject=m.p(subj, 'subject_code'),
                        term=m.p(term, 'term_code'), status=m.status(rec),
                        unmet_prerequisite=m.p(pre, 'subject_code'),
                        prerequisite_history='never attempted' if not attempts else
                        ', '.join(f"{a['term']} {a['outcome']}" for a in attempts),
                        root_cause=cause))
    return sorted(out, key=lambda r: (r['root_cause'], r['program'] or '', r['student_no'], r['subject']))


def w1_profile(m, student_no):
    s = m.seek_prop('Student', 'student_no', student_no)
    sp = m.person(s)
    programs = []
    for _, e in m.exp(s, 'HAS_ENROLMENT', 'out'):
        for _, pr in m.exp(e, 'IN_PROGRAM', 'out'):
            programs.append(f"{m.p(pr, 'program_code')} ({m.p(e, 'enrolment_status')})")
    subjects = []
    for rec, o in m.took_out(s):
        outcome = m.result(rec, 'grade_letter') or m.result(rec, 'competency_outcome') or m.status(rec)
        subjects.append(f"{m.p(o, 'subject_code')} {m.p(o, 'term_code')} {outcome}")
    guardians = []
    for _, gd in m.exp(s, 'GUARDIAN_OF', 'in'):
        gp = m.person(gd)
        contact = m.phone(gp, 'MOBILE') or m.phone(gp, 'HOME') or m.phone(gp, 'WORK') or ''
        guardians.append(f"{m.name(gp)} {contact}")
    return dict(student=m.name(sp), mobile=m.phone(sp, 'MOBILE'), home_phone=m.phone(sp, 'HOME'),
                programs=sorted(programs), subjects=sorted(subjects), guardians=sorted(guardians))


def w2_statement(m, account_no):
    b = m.seek('BillingAccount', account_no=account_no)
    out = []
    for _, holder in m.exp(b, 'HOLDS_ACCOUNT', 'in'):
        invs = [i for _, i in m.exp(b, 'BILLED_TO', 'in')]
        if m.has(holder, 'HostEmployer'):
            name, contact = m.p(holder, 'employer_name'), m.p(holder, 'contact_email')
        else:
            hp = m.person(holder)
            name = m.name(hp)
            contact = m.phone(hp, 'MOBILE') or m.phone(hp, 'HOME') or m.phone(hp, 'WORK') or m.p(hp, 'email')
        billed = paid = bal = 0.0
        for i in invs:
            t, pd, bl = m.totals(i)
            billed += t
            paid += pd
            bal += bl
        out.append(dict(account=m.p(b, 'account_no'), holder_name=name, contact=contact,
                        invoices=len(invs), billed=round(billed, 2), paid=round(paid, 2),
                        balance_owing=round(bal, 2)))
    return out


def run_workload(g):
    """Execute the six workload queries; return {query: (result, cost)}."""
    from replica import rows
    m = Meter(g)
    res = {}
    for key, fn in (('Q1', q1_conflict), ('Q2', q2_bluecard), ('Q3', q3_debt), ('Q4', q4_prereq)):
        m.reset()
        r = fn(m)
        res[key] = (r, m.cost())
    # W1/W2 are point lookups: executed once per key and averaged
    for key, fn, keys in (('W1', w1_profile, [r['student_no'] for r in rows('student')]),
                          ('W2', w2_statement, [r['account_no'] for r in rows('billing_account')])):
        results, costs = [], defaultdict(float)
        for k in keys:
            m.reset()
            results.append(fn(m, k))
            for c, v in m.cost().items():
                costs[c] += v
        res[key] = (results, {c: v / len(keys) for c, v in costs.items()})
    return res


if __name__ == '__main__':
    import json
    from variants import build
    g = build(name='B')
    res = run_workload(g)
    for k in ('Q1', 'Q2', 'Q3', 'Q4'):
        print(f'==== {k}  cost={res[k][1]}')
        for r in res[k][0]:
            print('  ', json.dumps(r, default=str))
