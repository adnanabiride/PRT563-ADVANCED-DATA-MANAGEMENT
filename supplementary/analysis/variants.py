"""
Parameterised graph builder used for the modelling experiment.

build(...) constructs the property graph from the 26 CSV files with each
modelling optimisation switched on or off independently:

  labels       O1  specialisation as extra labels on one node      (off: subtype node + IS_A hop)
  fold         O2  SUBJECT_ENROLMENT as [:TOOK] with RESULT folded (off: SubjectEnrolment + Result nodes)
  pivot        O3  PERSON_PHONE pivoted onto Person properties      (off: PhoneNumber nodes + HAS_PHONE)
  materialise  O4  Invoice total/paid/balance stored on the node    (off: computed from lines and payments)
  next_term    O5  [:NEXT_TERM] chain between consecutive terms     (off: ordering by date at query time)
  typed        --  dates/integers/decimals/booleans typed           (off: every value stored as a string)
  fk_copies    --  foreign-key columns ALSO kept as properties      (on only in the naive baseline)
  holds_key    --  account_no copied onto [:HOLDS_ACCOUNT] for the category constraint

build() with the defaults reproduces Model B (import.txt); build(**BASELINE)
reproduces Model A (supplementary/import_baseline.txt). Both equivalences are
asserted by signature() in __main__.
"""
import datetime
from collections import Counter as Multiset
from replica import rows, PG, build_model_a, build_model_b

OPTIMISATIONS = ('labels', 'fold', 'pivot', 'materialise', 'next_term')
BASELINE = dict(labels=False, fold=False, pivot=False, materialise=False, next_term=False,
                typed=False, fk_copies=True, holds_key=False)


def build(labels=True, fold=True, pivot=True, materialise=True, next_term=True,
          typed=True, fk_copies=False, holds_key=True, name=None):
    g = PG(name or 'variant')

    def s(v):                      # string column, '' -> null
        return v if v != '' else None

    def D(v):
        return (datetime.date.fromisoformat(v) if typed else v) if v != '' else None

    def I(v):
        return (int(v) if typed else v) if v != '' else None

    def F(v):
        return (float(v) if typed else v) if v != '' else None

    def B(v):
        return (v == 'Y') if typed else v

    # ---- reference nodes --------------------------------------------------------
    for r in rows('campus'):
        n = g.merge_node('Campus', {'campus_code': r['campus_code']})
        g.set(n, campus_name=s(r['campus_name']), suburb=s(r['suburb']), state=s(r['state']),
              postcode=s(r['postcode']), opened_date=D(r['opened_date']))
    for r in rows('term'):
        n = g.merge_node('Term', {'term_code': r['term_code']})
        g.set(n, academic_year=I(r['academic_year']), term_number=I(r['term_number']),
              start_date=D(r['start_date']), end_date=D(r['end_date']))
    for r in rows('program'):
        n = g.merge_node('Program', {'program_code': r['program_code']})
        g.set(n, program_name=s(r['program_name']), aqf_level=I(r['aqf_level']),
              duration_terms=I(r['duration_terms']))
    for r in rows('subject'):
        n = g.merge_node('Subject', {'subject_code': r['subject_code']})
        g.set(n, subject_title=s(r['subject_title']), nominal_hours=I(r['nominal_hours']))
        if not labels:
            g.set(n, subject_kind=s(r['subject_kind']))
    for table, lab, cols in [('qcaa_subject', 'QCAASubject', (('syllabus_year', I), ('subject_category', s))),
                             ('vet_unit', 'VETUnit', (('uoc_code', s), ('training_package_code', s)))]:
        for r in rows(table):
            if labels:
                n = g.find('Subject', subject_code=r['subject_code'])
                g.add_label(n, lab)
            else:
                n = g.merge_node(lab, {'subject_code': r['subject_code']})
                g.merge_rel('IS_A', n, g.find('Subject', subject_code=r['subject_code']))
            g.set(n, **{c: f(r[c]) for c, f in cols})
    for r in rows('host_employer'):
        n = g.merge_node('HostEmployer', {'employer_abn': r['employer_abn']})
        g.set(n, employer_name=s(r['employer_name']), industry_sector=s(r['industry_sector']),
              contact_email=s(r['contact_email']))
    for r in rows('billing_account'):
        n = g.merge_node('BillingAccount', {'account_no': r['account_no']})
        g.set(n, account_opened=D(r['account_opened']), account_status=s(r['account_status']))
    for r in rows('placement_agreement'):
        n = g.merge_node('PlacementAgreement', {'agreement_id': r['agreement_id']})
        g.set(n, signed_date=D(r['signed_date']), expiry_date=D(r['expiry_date']),
              insurance_policy_no=s(r['insurance_policy_no']))
    # ---- people ---------------------------------------------------------------------
    for r in rows('person'):
        n = g.merge_node('Person', {'person_id': r['person_id']})
        g.set(n, given_name=s(r['given_name']), family_name=s(r['family_name']),
              preferred_name=s(r['preferred_name']), date_of_birth=D(r['date_of_birth']),
              email=s(r['email']), street_address=s(r['street_address']), suburb=s(r['suburb']),
              state=s(r['state']), postcode=s(r['postcode']))
    for r in rows('person_phone'):
        p = g.find('Person', person_id=r['person_id'])
        if pivot:
            key = {'MOBILE': 'phone_mobile', 'HOME': 'phone_home', 'WORK': 'phone_work'}[r['phone_type']]
            g.set(p, **{key: r['phone_number']})
        else:
            ph = g.merge_node('PhoneNumber', {'person_id': r['person_id'], 'phone_number': r['phone_number']})
            g.set(ph, phone_type=r['phone_type'])
            g.merge_rel('HAS_PHONE', p, ph)
    role_cols = {
        'Student': (('student_no', s), ('usi', s), ('year_level', I), ('commenced_date', D)),
        'Staff': (('staff_no', s), ('position_title', s), ('employment_type', s), ('blue_card_expiry', D)),
        'Guardian': (('preferred_contact', s),),
    }
    for table, lab in (('student', 'Student'), ('staff', 'Staff'), ('guardian', 'Guardian')):
        for r in rows(table):
            p = g.find('Person', person_id=r['person_id'])
            if labels:
                g.add_label(p, lab, {'person_id': r['person_id']})
                n = p
            else:
                n = g.merge_node(lab, {'person_id': r['person_id']})
                g.merge_rel('IS_A', n, p)
            g.set(n, **{c: f(r[c]) for c, f in role_cols[lab]})
    # ---- reified relationships and dependent entities ---------------------------------
    for r in rows('course_offering'):
        n = g.merge_node('CourseOffering', {'subject_code': r['subject_code'], 'campus_code': r['campus_code'],
                                            'term_code': r['term_code']})
        g.set(n, delivery_mode=s(r['delivery_mode']), max_capacity=I(r['max_capacity']))
    for r in rows('enrolment'):
        n = g.merge_node('Enrolment', {'student_person_id': r['student_person_id'],
                                       'program_code': r['program_code']})
        g.set(n, enrolment_date=D(r['enrolment_date']), enrolment_status=s(r['enrolment_status']),
              funding_source=s(r['funding_source']))
        if fk_copies:
            g.set(n, campus_code=s(r['campus_code']))
    for r in rows('qualification'):
        n = g.merge_node('Qualification', {'qualification_id': r['qualification_id']})
        g.set(n, qualification_name=s(r['qualification_name']), certificate_no=s(r['certificate_no']),
              awarded_date=D(r['awarded_date']))
        if fk_copies:
            g.set(n, student_person_id=s(r['student_person_id']), program_code=s(r['program_code']))
    for r in rows('placement'):
        n = g.merge_node('Placement', {'student_person_id': r['student_person_id'],
                                       'employer_abn': r['employer_abn'], 'start_date': D(r['start_date'])})
        g.set(n, end_date=D(r['end_date']), hours_per_week=I(r['hours_per_week']))
    for r in rows('invoice'):
        n = g.merge_node('Invoice', {'invoice_no': r['invoice_no']})
        g.set(n, issue_date=D(r['issue_date']), due_date=D(r['due_date']), invoice_status=s(r['invoice_status']))
        if fk_copies:
            g.set(n, student_person_id=s(r['student_person_id']), term_code=s(r['term_code']))
    for r in rows('invoice_line'):
        n = g.merge_node('InvoiceLine', {'invoice_no': r['invoice_no'], 'line_no': I(r['line_no'])})
        g.set(n, description=s(r['description']), line_amount=F(r['line_amount']))
    for r in rows('payment'):
        n = g.merge_node('Payment', {'payment_id': r['payment_id']})
        g.set(n, paid_date=D(r['paid_date']), amount_paid=F(r['amount_paid']), payment_method=s(r['payment_method']))
        if fk_copies:
            g.set(n, invoice_no=s(r['invoice_no']))
    if not fold:
        for r in rows('subject_enrolment'):
            n = g.merge_node('SubjectEnrolment', {k: r[k] for k in ('student_person_id', 'subject_code',
                                                                  'campus_code', 'term_code')})
            g.set(n, enrolled_on=D(r['enrolled_on']), se_status=s(r['se_status']))
        for r in rows('result'):
            n = g.merge_node('Result', {k: r[k] for k in ('student_person_id', 'subject_code',
                                                        'campus_code', 'term_code')})
            g.set(n, result_type=s(r['result_type']), grade_letter=s(r['grade_letter']),
                  competency_outcome=s(r['competency_outcome']), awarded_date=D(r['awarded_date']))
    # ---- relationships ----------------------------------------------------------------
    for r in rows('guardianship'):
        g.merge_rel('GUARDIAN_OF', g.find('Guardian', person_id=r['guardian_person_id']),
                    g.find('Student', person_id=r['student_person_id']),
                    relationship_type=r['relationship_type'], is_primary_contact=B(r['is_primary_contact']))
    for r in rows('staff'):
        if r['supervisor_person_id']:
            g.merge_rel('SUPERVISES', g.find('Staff', person_id=r['supervisor_person_id']),
                        g.find('Staff', person_id=r['person_id']))
    for r in rows('program_subject'):
        g.merge_rel('INCLUDES', g.find('Program', program_code=r['program_code']),
                    g.find('Subject', subject_code=r['subject_code']),
                    is_core=B(r['is_core']), sequence_no=I(r['sequence_no']))
    for r in rows('subject_prerequisite'):
        g.merge_rel('REQUIRES', g.find('Subject', subject_code=r['subject_code']),
                    g.find('Subject', subject_code=r['prerequisite_code']))
    for r in rows('course_offering'):
        o = g.find('CourseOffering', subject_code=r['subject_code'], campus_code=r['campus_code'],
                   term_code=r['term_code'])
        g.merge_rel('OF_SUBJECT', o, g.find('Subject', subject_code=r['subject_code']))
        g.merge_rel('AT_CAMPUS', o, g.find('Campus', campus_code=r['campus_code']))
        g.merge_rel('IN_TERM', o, g.find('Term', term_code=r['term_code']))
        g.merge_rel('LEADS', g.find('Staff', person_id=r['lead_staff_id']), o)
    if fold:
        for r in rows('subject_enrolment'):
            g.merge_rel('TOOK', g.find('Student', person_id=r['student_person_id']),
                        g.find('CourseOffering', subject_code=r['subject_code'], campus_code=r['campus_code'],
                               term_code=r['term_code']),
                        enrolled_on=D(r['enrolled_on']), status=s(r['se_status']))
        for r in rows('result'):
            g.merge_rel('TOOK', g.find('Student', person_id=r['student_person_id']),
                        g.find('CourseOffering', subject_code=r['subject_code'], campus_code=r['campus_code'],
                               term_code=r['term_code']),
                        result_type=s(r['result_type']), grade_letter=s(r['grade_letter']),
                        competency_outcome=s(r['competency_outcome']), awarded_date=D(r['awarded_date']))
    else:
        for r in rows('subject_enrolment'):
            k = {c: r[c] for c in ('student_person_id', 'subject_code', 'campus_code', 'term_code')}
            se = g.find('SubjectEnrolment', **k)
            g.merge_rel('HAS_SUBJECT_ENROLMENT', g.find('Student', person_id=r['student_person_id']), se)
            g.merge_rel('FOR_OFFERING', se, g.find('CourseOffering', subject_code=r['subject_code'],
                                                   campus_code=r['campus_code'], term_code=r['term_code']))
        for r in rows('result'):
            k = {c: r[c] for c in ('student_person_id', 'subject_code', 'campus_code', 'term_code')}
            g.merge_rel('HAS_RESULT', g.find('SubjectEnrolment', **k), g.find('Result', **k))
    for r in rows('enrolment'):
        e = g.find('Enrolment', student_person_id=r['student_person_id'], program_code=r['program_code'])
        g.merge_rel('HAS_ENROLMENT', g.find('Student', person_id=r['student_person_id']), e)
        g.merge_rel('IN_PROGRAM', e, g.find('Program', program_code=r['program_code']))
        g.merge_rel('AT_CAMPUS', e, g.find('Campus', campus_code=r['campus_code']))
    for r in rows('qualification'):
        g.merge_rel('AWARDED', g.find('Enrolment', student_person_id=r['student_person_id'],
                                      program_code=r['program_code']),
                    g.find('Qualification', qualification_id=r['qualification_id']))
    for r in rows('placement'):
        pl = g.find('Placement', student_person_id=r['student_person_id'], employer_abn=r['employer_abn'],
                    start_date=D(r['start_date']))
        g.merge_rel('UNDERTAKES', g.find('Student', person_id=r['student_person_id']), pl)
        g.merge_rel('HOSTED_BY', pl, g.find('HostEmployer', employer_abn=r['employer_abn']))
        g.merge_rel('GOVERNED_BY', pl, g.find('PlacementAgreement', agreement_id=r['agreement_id']))
    for table, lab, key in (('student', 'Student', 'person_id'), ('guardian', 'Guardian', 'person_id'),
                            ('host_employer', 'HostEmployer', 'employer_abn')):
        for r in rows(table):
            if r['account_no']:
                props = {'account_no': r['account_no']} if holds_key else {}
                g.merge_rel('HOLDS_ACCOUNT', g.find(lab, **{key: r[key]}),
                            g.find('BillingAccount', account_no=r['account_no']), **props)
    for r in rows('invoice'):
        i = g.find('Invoice', invoice_no=r['invoice_no'])
        g.merge_rel('BILLED_TO', i, g.find('BillingAccount', account_no=r['account_no']))
        g.merge_rel('RAISED_FOR', i, g.find('Student', person_id=r['student_person_id']))
        g.merge_rel('FOR_TERM', i, g.find('Term', term_code=r['term_code']))
    for r in rows('invoice_line'):
        g.merge_rel('HAS_LINE', g.find('Invoice', invoice_no=r['invoice_no']),
                    g.find('InvoiceLine', invoice_no=r['invoice_no'], line_no=I(r['line_no'])))
    for r in rows('payment'):
        g.merge_rel('SETTLES', g.find('Payment', payment_id=r['payment_id']),
                    g.find('Invoice', invoice_no=r['invoice_no']))
    # ---- derived structures --------------------------------------------------------------
    if next_term:
        terms = sorted([n for n, v in g.nodes.items() if 'Term' in v['labels']],
                       key=lambda n: (int(g.nodes[n]['props']['academic_year']),
                                      int(g.nodes[n]['props']['term_number'])))
        for a, b in zip(terms, terms[1:]):
            g.merge_rel('NEXT_TERM', a, b)
    if materialise:
        for n, v in g.nodes.items():
            if 'Invoice' in v['labels']:
                total = sum(float(g.nodes[g.rels[x]['end']]['props']['line_amount']) for x in g.out[n]['HAS_LINE'])
                paid = sum(float(g.nodes[g.rels[x]['start']]['props']['amount_paid']) for x in g.inn[n]['SETTLES'])
                v['props'].update(total_amount=float(total), amount_paid=float(paid),
                                  balance_owing=float(total - paid))
    # remember the switches so query plans can branch on them
    g.flags = dict(labels=labels, fold=fold, pivot=pivot, materialise=materialise, next_term=next_term,
                   typed=typed)
    return g


def signature(g):
    """Order-independent fingerprint of a property graph (labels, properties, topology)."""
    def nkey(n):
        v = g.nodes[n]
        return (tuple(sorted(v['labels'])), tuple(sorted((k, str(x)) for k, x in v['props'].items())))
    nodes = Multiset(nkey(n) for n in g.nodes)
    rels = Multiset((r['type'], nkey(r['start']), nkey(r['end']),
                     tuple(sorted((k, str(x)) for k, x in r['props'].items()))) for r in g.rels.values())
    return nodes, rels


if __name__ == '__main__':
    b1, b2 = build(name='B'), build_model_b()
    a1, a2 = build(name='A', **BASELINE), build_model_a()
    assert signature(b1) == signature(b2), 'Model B mismatch'
    assert signature(a1) == signature(a2), 'Model A mismatch'
    print('variants.build() reproduces Model A and Model B exactly')
    for gg in (a1, b1):
        print(gg.name, len(gg.nodes), 'nodes', len(gg.rels), 'rels', gg.prop_count(), 'props')
