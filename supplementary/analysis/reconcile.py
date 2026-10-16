"""Cell-level reconciliation: every column of every relational row must be
recoverable from Model B (as a property, a label, or a relationship)."""
import json, datetime
from replica import build_model_b, rows

g = build_model_b()


def val(v):
    if isinstance(v, (datetime.date,)):
        return v.isoformat()
    if isinstance(v, bool):
        return 'Y' if v else 'N'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return '' if v is None else str(v)


def prop(n, k):
    return val(g.nodes[n]['props'].get(k))


def rel_exists(typ, a, b):
    ok = any(g.rels[r]['end'] == b for r in g.out[a][typ])
    if ok and typ == 'HOLDS_ACCOUNT':      # category key copied onto the relationship
        ok = all(g.rels[r]['props'].get('account_no') == g.nodes[b]['props']['account_no']
                 for r in g.out[a][typ] if g.rels[r]['end'] == b)
    return ok


def rel_props(typ, a, b):
    for r in g.out[a][typ]:
        if g.rels[r]['end'] == b:
            return g.rels[r]['props']
    return None


report = []   # (table, rows, cells_checked, mismatches, target)
mism = []


def check(table, target, fn):
    rs = rows(table)
    cells = 0
    bad = 0
    for r in rs:
        for col, ok in fn(r):
            cells += 1
            if not ok:
                bad += 1
                mism.append((table, col, r))
    report.append((table, len(rs), cells, bad, target))


def node_cols(label, keycols, skip=(), fks=None):
    fks = fks or {}

    def fn(r):
        n = g.find(label, **{k: (int(r[k]) if k == 'line_no' else
                                 (datetime.date.fromisoformat(r[k]) if k == 'start_date' else r[k]))
                             for k in keycols})
        out = [('__node__', n is not None)]
        if n is None:
            return out
        for col, v in r.items():
            if col in skip:
                continue
            if col in fks:
                typ, olabel, okey, direction = fks[col]
                if v == '':
                    out.append((col, True))
                    continue
                other = g.find(olabel, **{okey: v})
                ok = rel_exists(typ, n, other) if direction == 'out' else rel_exists(typ, other, n)
                out.append((col, ok))
            else:
                out.append((col, prop(n, col) == v))
        return out
    return fn


check('campus', ':Campus', node_cols('Campus', ['campus_code']))
check('term', ':Term', node_cols('Term', ['term_code']))
check('program', ':Program', node_cols('Program', ['program_code']))


def subject_fn(r):
    n = g.find('Subject', subject_code=r['subject_code'])
    out = [('__node__', n is not None)]
    for col, v in r.items():
        if col == 'subject_kind':
            lab = {'QCAA': 'QCAASubject', 'VET': 'VETUnit'}[v]
            out.append((col, g.has(n, lab)))
        else:
            out.append((col, prop(n, col) == v))
    return out


check('subject', ':Subject (+ label as discriminator)', subject_fn)
check('qcaa_subject', ':Subject:QCAASubject', node_cols('QCAASubject', ['subject_code']) if False else
      (lambda r: [('__label__', g.has(g.find('Subject', subject_code=r['subject_code']), 'QCAASubject'))] +
       [(c, prop(g.find('Subject', subject_code=r['subject_code']), c) == v) for c, v in r.items()]))
check('vet_unit', ':Subject:VETUnit',
      lambda r: [('__label__', g.has(g.find('Subject', subject_code=r['subject_code']), 'VETUnit'))] +
      [(c, prop(g.find('Subject', subject_code=r['subject_code']), c) == v) for c, v in r.items()])
check('host_employer', ':HostEmployer + HOLDS_ACCOUNT',
      node_cols('HostEmployer', ['employer_abn'],
                fks={'account_no': ('HOLDS_ACCOUNT', 'BillingAccount', 'account_no', 'out')}))
check('billing_account', ':BillingAccount', node_cols('BillingAccount', ['account_no']))
check('placement_agreement', ':PlacementAgreement', node_cols('PlacementAgreement', ['agreement_id']))
check('person', ':Person', node_cols('Person', ['person_id']))


def phone_fn(r):
    n = g.find('Person', person_id=r['person_id'])
    key = {'MOBILE': 'phone_mobile', 'HOME': 'phone_home', 'WORK': 'phone_work'}[r['phone_type']]
    return [('phone_number+type', prop(n, key) == r['phone_number']), ('person_id', n is not None)]


check('person_phone', 'Person.phone_mobile / phone_home / phone_work', phone_fn)


def role_fn(label, fks=None):
    fks = fks or {}

    def fn(r):
        n = g.find(label, person_id=r['person_id'])
        out = [('__label__', n is not None and g.has(n, label))]
        for col, v in r.items():
            if col == 'person_id':
                continue
            if col in fks:
                typ, olabel, okey, direction = fks[col]
                if v == '':
                    out.append((col, True))
                    continue
                other = g.find(olabel, **{okey: v})
                out.append((col, rel_exists(typ, n, other) if direction == 'out' else rel_exists(typ, other, n)))
            else:
                out.append((col, prop(n, col) == v))
        return out
    return fn


check('student', ':Person:Student + HOLDS_ACCOUNT',
      role_fn('Student', {'account_no': ('HOLDS_ACCOUNT', 'BillingAccount', 'account_no', 'out')}))
check('staff', ':Person:Staff + SUPERVISES',
      role_fn('Staff', {'supervisor_person_id': ('SUPERVISES', 'Staff', 'person_id', 'in')}))
check('guardian', ':Person:Guardian + HOLDS_ACCOUNT',
      role_fn('Guardian', {'account_no': ('HOLDS_ACCOUNT', 'BillingAccount', 'account_no', 'out')}))
check('course_offering', ':CourseOffering + OF_SUBJECT/AT_CAMPUS/IN_TERM/LEADS',
      node_cols('CourseOffering', ['subject_code', 'campus_code', 'term_code'],
                fks={'lead_staff_id': ('LEADS', 'Staff', 'person_id', 'in')}))
check('enrolment', ':Enrolment + HAS_ENROLMENT/IN_PROGRAM/AT_CAMPUS',
      node_cols('Enrolment', ['student_person_id', 'program_code'],
                fks={'campus_code': ('AT_CAMPUS', 'Campus', 'campus_code', 'out')}))
check('qualification', ':Qualification + AWARDED',
      lambda r: [('__node__', g.find('Qualification', qualification_id=r['qualification_id']) is not None)] +
      [(c, prop(g.find('Qualification', qualification_id=r['qualification_id']), c) == v)
       for c, v in r.items() if c not in ('student_person_id', 'program_code')] +
      [('enrolment_fk', rel_exists('AWARDED', g.find('Enrolment', student_person_id=r['student_person_id'],
                                                      program_code=r['program_code']),
                                   g.find('Qualification', qualification_id=r['qualification_id'])))])
check('placement', ':Placement + UNDERTAKES/HOSTED_BY/GOVERNED_BY',
      node_cols('Placement', ['student_person_id', 'employer_abn', 'start_date'],
                fks={'agreement_id': ('GOVERNED_BY', 'PlacementAgreement', 'agreement_id', 'out')}))
check('invoice', ':Invoice + BILLED_TO/RAISED_FOR/FOR_TERM',
      node_cols('Invoice', ['invoice_no'],
                fks={'account_no': ('BILLED_TO', 'BillingAccount', 'account_no', 'out'),
                     'student_person_id': ('RAISED_FOR', 'Student', 'person_id', 'out'),
                     'term_code': ('FOR_TERM', 'Term', 'term_code', 'out')}))
check('invoice_line', ':InvoiceLine + HAS_LINE',
      lambda r: [('__node__', g.find('InvoiceLine', invoice_no=r['invoice_no'], line_no=int(r['line_no'])) is not None),
                 ('description', prop(g.find('InvoiceLine', invoice_no=r['invoice_no'], line_no=int(r['line_no'])), 'description') == r['description']),
                 ('line_amount', prop(g.find('InvoiceLine', invoice_no=r['invoice_no'], line_no=int(r['line_no'])), 'line_amount') == r['line_amount']),
                 ('owner', rel_exists('HAS_LINE', g.find('Invoice', invoice_no=r['invoice_no']),
                                      g.find('InvoiceLine', invoice_no=r['invoice_no'], line_no=int(r['line_no']))))])
check('payment', ':Payment + SETTLES',
      node_cols('Payment', ['payment_id'],
                fks={'invoice_no': ('SETTLES', 'Invoice', 'invoice_no', 'out')}))


def rel_fn(typ, alabel, akey, acol, blabel, bkey, bcol, propmap):
    def fn(r):
        a = g.find(alabel, **{akey: r[acol]})
        b = g.find(blabel, **{bkey: r[bcol]})
        ps = rel_props(typ, a, b)
        out = [('__rel__', ps is not None)]
        for col, pkey in propmap.items():
            out.append((col, ps is not None and val(ps.get(pkey)) == r[col]))
        return out
    return fn


check('guardianship', '[:GUARDIAN_OF {relationship_type, is_primary_contact}]',
      rel_fn('GUARDIAN_OF', 'Guardian', 'person_id', 'guardian_person_id', 'Student', 'person_id',
             'student_person_id', {'relationship_type': 'relationship_type', 'is_primary_contact': 'is_primary_contact'}))
check('program_subject', '[:INCLUDES {is_core, sequence_no}]',
      rel_fn('INCLUDES', 'Program', 'program_code', 'program_code', 'Subject', 'subject_code', 'subject_code',
             {'is_core': 'is_core', 'sequence_no': 'sequence_no'}))
check('subject_prerequisite', '[:REQUIRES]',
      rel_fn('REQUIRES', 'Subject', 'subject_code', 'subject_code', 'Subject', 'subject_code', 'prerequisite_code', {}))


def took_fn(cols):
    def fn(r):
        a = g.find('Student', person_id=r['student_person_id'])
        b = g.find('CourseOffering', subject_code=r['subject_code'], campus_code=r['campus_code'], term_code=r['term_code'])
        ps = rel_props('TOOK', a, b)
        out = [('__rel__', ps is not None)]
        for col, pkey in cols.items():
            out.append((col, ps is not None and val(ps.get(pkey)) == r[col]))
        return out
    return fn


check('subject_enrolment', '[:TOOK {enrolled_on, status}]',
      took_fn({'enrolled_on': 'enrolled_on', 'se_status': 'status'}))
check('result', 'folded onto [:TOOK] {result_type, grade_letter, competency_outcome, awarded_date}',
      took_fn({'result_type': 'result_type', 'grade_letter': 'grade_letter',
               'competency_outcome': 'competency_outcome', 'awarded_date': 'awarded_date'}))

tot_rows = sum(x[1] for x in report)
tot_cells = sum(x[2] for x in report)
tot_bad = sum(x[3] for x in report)
for t, n, c, b, target in report:
    print(f"{t:22} {n:4} rows {c:5} checks {b:3} mismatches -> {target}")
print(f"\nTOTAL {tot_rows} rows, {tot_cells} checks, {tot_bad} mismatches")
for m in mism[:10]:
    print('MISMATCH', m)
json.dump({'tables': [dict(table=t, rows=n, checks=c, mismatches=b, target=target) for t, n, c, b, target in report],
           'rows': tot_rows, 'checks': tot_cells, 'mismatches': tot_bad},
          open('results_reconciliation.json', 'w'), indent=1)
