"""
In-memory replica of the two Neo4j graph models, built from the same CSV files
with the same mapping rules as import.txt (Model B) and import_baseline.txt
(Model A). Used to reconcile the migration, compute expected query results and
measure engine-independent traversal cost.
"""
import csv, os, datetime
from collections import defaultdict

CSV_DIR = os.environ.get('TIS_CSV_DIR',
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'csv'))


def rows(name):
    with open(os.path.join(CSV_DIR, name + '.csv'), newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def d(s):
    return datetime.date.fromisoformat(s) if s else None


def nz(s):          # CASE WHEN x <> '' THEN x END
    return s if s != '' else None


class Counter:
    """Counts relationship expansions and node/property touches."""
    def __init__(self):
        self.expansions = 0
        self.nodes = set()
        self.prop_reads = 0

    def reset(self):
        self.expansions = 0
        self.nodes = set()
        self.prop_reads = 0


class PG:
    def __init__(self, name):
        self.name = name
        self.nodes = {}                       # nid -> {'labels': set, 'props': {}}
        self.rels = {}                        # rid -> {'type','start','end','props'}
        self.out = defaultdict(lambda: defaultdict(list))
        self.inn = defaultdict(lambda: defaultdict(list))
        self.key = {}                         # (label, keytuple) -> nid
        self._n = 0
        self._r = 0
        self.c = Counter()

    # ---- construction -------------------------------------------------------
    def merge_node(self, label, keyprops):
        k = (label, tuple(sorted(keyprops.items())))
        if k in self.key:
            return self.key[k]
        self._n += 1
        nid = self._n
        self.nodes[nid] = {'labels': {label}, 'props': dict(keyprops)}
        self.key[k] = nid
        return nid

    def find(self, label, **keyprops):
        k = (label, tuple(sorted(keyprops.items())))
        return self.key.get(k)

    def add_label(self, nid, label, keyprops=None):
        self.nodes[nid]['labels'].add(label)
        if keyprops:
            self.key[(label, tuple(sorted(keyprops.items())))] = nid

    def set(self, nid, **props):
        for k, v in props.items():
            if v is None:
                self.nodes[nid]['props'].pop(k, None)
            else:
                self.nodes[nid]['props'][k] = v

    def merge_rel(self, typ, a, b, **props):
        for rid in self.out[a][typ]:
            if self.rels[rid]['end'] == b:
                self.rels[rid]['props'].update({k: v for k, v in props.items() if v is not None})
                return rid
        self._r += 1
        rid = self._r
        self.rels[rid] = {'type': typ, 'start': a, 'end': b,
                          'props': {k: v for k, v in props.items() if v is not None}}
        self.out[a][typ].append(rid)
        self.inn[b][typ].append(rid)
        return rid

    # ---- instrumented traversal --------------------------------------------
    def label_scan(self, label):
        res = [n for n, v in self.nodes.items() if label in v['labels']]
        for n in res:
            self.c.nodes.add(n)
        return res

    def seek(self, label, **keyprops):
        n = self.find(label, **keyprops)
        if n:
            self.c.nodes.add(n)
        return n

    def expand(self, nid, typ, direction='out'):
        """Yield (rel, other_node) and count one expansion per relationship."""
        adj = self.out if direction == 'out' else self.inn
        out = []
        for rid in adj[nid][typ]:
            self.c.expansions += 1
            r = self.rels[rid]
            other = r['end'] if direction == 'out' else r['start']
            self.c.nodes.add(other)
            out.append((r, other))
        return out

    def p(self, nid, key):
        self.c.prop_reads += 1
        return self.nodes[nid]['props'].get(key)

    def rp(self, r, key):
        self.c.prop_reads += 1
        return r['props'].get(key)

    def has(self, nid, label):
        return label in self.nodes[nid]['labels']

    # ---- summaries ------------------------------------------------------------
    def label_counts(self):
        cnt = defaultdict(int)
        for v in self.nodes.values():
            for l in v['labels']:
                cnt[l] += 1
        return dict(sorted(cnt.items()))

    def type_counts(self):
        cnt = defaultdict(int)
        for r in self.rels.values():
            cnt[r['type']] += 1
        return dict(sorted(cnt.items()))

    def prop_count(self):
        return (sum(len(v['props']) for v in self.nodes.values()) +
                sum(len(r['props']) for r in self.rels.values()))


# =============================================================================
# MODEL B - optimised (mirrors repo/import.txt section by section)
# =============================================================================
def build_model_b():
    g = PG('B')
    # 3.1
    for r in rows('campus'):
        n = g.merge_node('Campus', {'campus_code': r['campus_code']})
        g.set(n, campus_name=r['campus_name'], suburb=r['suburb'], state=r['state'],
              postcode=r['postcode'], opened_date=d(r['opened_date']))
    # 3.2
    for r in rows('term'):
        n = g.merge_node('Term', {'term_code': r['term_code']})
        g.set(n, academic_year=int(r['academic_year']), term_number=int(r['term_number']),
              start_date=d(r['start_date']), end_date=d(r['end_date']))
    # 3.3
    for r in rows('program'):
        n = g.merge_node('Program', {'program_code': r['program_code']})
        g.set(n, program_name=r['program_name'], aqf_level=int(r['aqf_level']),
              duration_terms=int(r['duration_terms']))
    # 3.4
    for r in rows('subject'):
        n = g.merge_node('Subject', {'subject_code': r['subject_code']})
        g.set(n, subject_title=r['subject_title'], nominal_hours=int(r['nominal_hours']))
    # 3.5
    for r in rows('qcaa_subject'):
        n = g.find('Subject', subject_code=r['subject_code'])
        g.add_label(n, 'QCAASubject')
        g.set(n, syllabus_year=int(r['syllabus_year']), subject_category=r['subject_category'])
    # 3.6
    for r in rows('vet_unit'):
        n = g.find('Subject', subject_code=r['subject_code'])
        g.add_label(n, 'VETUnit')
        g.set(n, uoc_code=r['uoc_code'], training_package_code=r['training_package_code'])
    # 3.7
    for r in rows('host_employer'):
        n = g.merge_node('HostEmployer', {'employer_abn': r['employer_abn']})
        g.set(n, employer_name=r['employer_name'], industry_sector=r['industry_sector'],
              contact_email=nz(r['contact_email']))
    # 3.8
    for r in rows('billing_account'):
        n = g.merge_node('BillingAccount', {'account_no': r['account_no']})
        g.set(n, account_opened=d(r['account_opened']), account_status=r['account_status'])
    # 3.9
    for r in rows('placement_agreement'):
        n = g.merge_node('PlacementAgreement', {'agreement_id': r['agreement_id']})
        g.set(n, signed_date=d(r['signed_date']), expiry_date=d(r['expiry_date']),
              insurance_policy_no=r['insurance_policy_no'])
    # 4.1
    for r in rows('person'):
        n = g.merge_node('Person', {'person_id': r['person_id']})
        g.set(n, given_name=r['given_name'], family_name=r['family_name'],
              preferred_name=r['preferred_name'], date_of_birth=d(r['date_of_birth']),
              email=nz(r['email']), street_address=r['street_address'], suburb=r['suburb'],
              state=r['state'], postcode=r['postcode'])
    # 4.2 phones pivoted
    for r in rows('person_phone'):
        n = g.find('Person', person_id=r['person_id'])
        key = {'MOBILE': 'phone_mobile', 'HOME': 'phone_home', 'WORK': 'phone_work'}[r['phone_type']]
        g.set(n, **{key: r['phone_number']})
    # 4.3-4.5 roles as labels on the same node (key lookups by person_id for each label)
    for r in rows('student'):
        n = g.find('Person', person_id=r['person_id'])
        g.add_label(n, 'Student', {'person_id': r['person_id']})
        g.set(n, student_no=r['student_no'], usi=nz(r['usi']), year_level=int(r['year_level']),
              commenced_date=d(r['commenced_date']))
    for r in rows('staff'):
        n = g.find('Person', person_id=r['person_id'])
        g.add_label(n, 'Staff', {'person_id': r['person_id']})
        g.set(n, staff_no=r['staff_no'], position_title=r['position_title'],
              employment_type=r['employment_type'], blue_card_expiry=d(r['blue_card_expiry']))
    for r in rows('guardian'):
        n = g.find('Person', person_id=r['person_id'])
        g.add_label(n, 'Guardian', {'person_id': r['person_id']})
        g.set(n, preferred_contact=r['preferred_contact'])
    # 5.1
    for r in rows('course_offering'):
        n = g.merge_node('CourseOffering', {'subject_code': r['subject_code'],
                                            'campus_code': r['campus_code'],
                                            'term_code': r['term_code']})
        g.set(n, delivery_mode=r['delivery_mode'], max_capacity=int(r['max_capacity']))
    # 5.2
    for r in rows('enrolment'):
        n = g.merge_node('Enrolment', {'student_person_id': r['student_person_id'],
                                       'program_code': r['program_code']})
        g.set(n, enrolment_date=d(r['enrolment_date']), enrolment_status=r['enrolment_status'],
              funding_source=r['funding_source'])
    # 5.3
    for r in rows('qualification'):
        n = g.merge_node('Qualification', {'qualification_id': r['qualification_id']})
        g.set(n, qualification_name=r['qualification_name'], certificate_no=r['certificate_no'],
              awarded_date=d(r['awarded_date']))
    # 5.4
    for r in rows('placement'):
        n = g.merge_node('Placement', {'student_person_id': r['student_person_id'],
                                       'employer_abn': r['employer_abn'],
                                       'start_date': d(r['start_date'])})
        g.set(n, end_date=d(r['end_date']), hours_per_week=int(r['hours_per_week']))
    # 5.5
    for r in rows('invoice'):
        n = g.merge_node('Invoice', {'invoice_no': r['invoice_no']})
        g.set(n, issue_date=d(r['issue_date']), due_date=d(r['due_date']),
              invoice_status=r['invoice_status'])
    # 5.6
    for r in rows('invoice_line'):
        n = g.merge_node('InvoiceLine', {'invoice_no': r['invoice_no'], 'line_no': int(r['line_no'])})
        g.set(n, description=r['description'], line_amount=float(r['line_amount']))
    # 5.7
    for r in rows('payment'):
        n = g.merge_node('Payment', {'payment_id': r['payment_id']})
        g.set(n, paid_date=d(r['paid_date']), amount_paid=float(r['amount_paid']),
              payment_method=r['payment_method'])
    # 6.1
    for r in rows('guardianship'):
        gd = g.find('Guardian', person_id=r['guardian_person_id'])
        st = g.find('Student', person_id=r['student_person_id'])
        g.merge_rel('GUARDIAN_OF', gd, st, relationship_type=r['relationship_type'],
                    is_primary_contact=(r['is_primary_contact'] == 'Y'))
    # 6.2
    for r in rows('staff'):
        if r['supervisor_person_id']:
            g.merge_rel('SUPERVISES', g.find('Staff', person_id=r['supervisor_person_id']),
                        g.find('Staff', person_id=r['person_id']))
    # 6.3
    for r in rows('program_subject'):
        g.merge_rel('INCLUDES', g.find('Program', program_code=r['program_code']),
                    g.find('Subject', subject_code=r['subject_code']),
                    is_core=(r['is_core'] == 'Y'), sequence_no=int(r['sequence_no']))
    # 6.4
    for r in rows('subject_prerequisite'):
        g.merge_rel('REQUIRES', g.find('Subject', subject_code=r['subject_code']),
                    g.find('Subject', subject_code=r['prerequisite_code']))
    # 6.5
    for r in rows('course_offering'):
        o = g.find('CourseOffering', subject_code=r['subject_code'], campus_code=r['campus_code'],
                   term_code=r['term_code'])
        g.merge_rel('OF_SUBJECT', o, g.find('Subject', subject_code=r['subject_code']))
        g.merge_rel('AT_CAMPUS', o, g.find('Campus', campus_code=r['campus_code']))
        g.merge_rel('IN_TERM', o, g.find('Term', term_code=r['term_code']))
        g.merge_rel('LEADS', g.find('Staff', person_id=r['lead_staff_id']), o)
    # 6.6
    for r in rows('subject_enrolment'):
        s = g.find('Student', person_id=r['student_person_id'])
        o = g.find('CourseOffering', subject_code=r['subject_code'], campus_code=r['campus_code'],
                   term_code=r['term_code'])
        g.merge_rel('TOOK', s, o, enrolled_on=d(r['enrolled_on']), status=r['se_status'])
    for r in rows('result'):
        s = g.find('Student', person_id=r['student_person_id'])
        o = g.find('CourseOffering', subject_code=r['subject_code'], campus_code=r['campus_code'],
                   term_code=r['term_code'])
        g.merge_rel('TOOK', s, o, result_type=r['result_type'], grade_letter=nz(r['grade_letter']),
                    competency_outcome=nz(r['competency_outcome']), awarded_date=d(r['awarded_date']))
    # 6.7
    for r in rows('enrolment'):
        e = g.find('Enrolment', student_person_id=r['student_person_id'], program_code=r['program_code'])
        g.merge_rel('HAS_ENROLMENT', g.find('Student', person_id=r['student_person_id']), e)
        g.merge_rel('IN_PROGRAM', e, g.find('Program', program_code=r['program_code']))
        g.merge_rel('AT_CAMPUS', e, g.find('Campus', campus_code=r['campus_code']))
    # 6.8
    for r in rows('qualification'):
        g.merge_rel('AWARDED', g.find('Enrolment', student_person_id=r['student_person_id'],
                                      program_code=r['program_code']),
                    g.find('Qualification', qualification_id=r['qualification_id']))
    # 6.9
    for r in rows('placement'):
        pl = g.find('Placement', student_person_id=r['student_person_id'], employer_abn=r['employer_abn'],
                    start_date=d(r['start_date']))
        g.merge_rel('UNDERTAKES', g.find('Student', person_id=r['student_person_id']), pl)
        g.merge_rel('HOSTED_BY', pl, g.find('HostEmployer', employer_abn=r['employer_abn']))
        g.merge_rel('GOVERNED_BY', pl, g.find('PlacementAgreement', agreement_id=r['agreement_id']))
    # 6.10
    for r in rows('student'):
        if r['account_no']:
            g.merge_rel('HOLDS_ACCOUNT', g.find('Student', person_id=r['person_id']),
                        g.find('BillingAccount', account_no=r['account_no']), account_no=r['account_no'])
    for r in rows('guardian'):
        if r['account_no']:
            g.merge_rel('HOLDS_ACCOUNT', g.find('Guardian', person_id=r['person_id']),
                        g.find('BillingAccount', account_no=r['account_no']), account_no=r['account_no'])
    for r in rows('host_employer'):
        if r['account_no']:
            g.merge_rel('HOLDS_ACCOUNT', g.find('HostEmployer', employer_abn=r['employer_abn']),
                        g.find('BillingAccount', account_no=r['account_no']), account_no=r['account_no'])
    # 6.11
    for r in rows('invoice'):
        i = g.find('Invoice', invoice_no=r['invoice_no'])
        g.merge_rel('BILLED_TO', i, g.find('BillingAccount', account_no=r['account_no']))
        g.merge_rel('RAISED_FOR', i, g.find('Student', person_id=r['student_person_id']))
        g.merge_rel('FOR_TERM', i, g.find('Term', term_code=r['term_code']))
    # 6.12
    for r in rows('invoice_line'):
        g.merge_rel('HAS_LINE', g.find('Invoice', invoice_no=r['invoice_no']),
                    g.find('InvoiceLine', invoice_no=r['invoice_no'], line_no=int(r['line_no'])))
    # 6.13
    for r in rows('payment'):
        g.merge_rel('SETTLES', g.find('Payment', payment_id=r['payment_id']),
                    g.find('Invoice', invoice_no=r['invoice_no']))
    # 7.1 NEXT_TERM
    terms = sorted([n for n, v in g.nodes.items() if 'Term' in v['labels']],
                   key=lambda n: (g.nodes[n]['props']['academic_year'], g.nodes[n]['props']['term_number']))
    for a, b in zip(terms, terms[1:]):
        g.merge_rel('NEXT_TERM', a, b)
    # 7.2 materialised invoice balance
    for n, v in g.nodes.items():
        if 'Invoice' in v['labels']:
            total = sum(g.nodes[r['end']]['props']['line_amount'] for r in
                        (g.rels[x] for x in g.out[n]['HAS_LINE']))
            paid = sum(g.nodes[r['start']]['props']['amount_paid'] for r in
                       (g.rels[x] for x in g.inn[n]['SETTLES']))
            v['props'].update(total_amount=float(total), amount_paid=float(paid),
                              balance_owing=float(total - paid))
    return g


# =============================================================================
# MODEL A - baseline direct translation (mirrors repo/supplementary/import_baseline.txt)
#   table -> label, row -> node (including subtype and dependent tables),
#   FK -> relationship, pure junction table -> relationship with properties.
# =============================================================================
def build_model_a():
    g = PG('A')
    simple = {
        'campus': ('Campus', ['campus_code']), 'term': ('Term', ['term_code']),
        'program': ('Program', ['program_code']), 'subject': ('Subject', ['subject_code']),
        'host_employer': ('HostEmployer', ['employer_abn']),
        'billing_account': ('BillingAccount', ['account_no']),
        'placement_agreement': ('PlacementAgreement', ['agreement_id']),
        'person': ('Person', ['person_id']),
        'student': ('Student', ['person_id']), 'staff': ('Staff', ['person_id']),
        'guardian': ('Guardian', ['person_id']),
        'qcaa_subject': ('QCAASubject', ['subject_code']), 'vet_unit': ('VETUnit', ['subject_code']),
        'course_offering': ('CourseOffering', ['subject_code', 'campus_code', 'term_code']),
        'enrolment': ('Enrolment', ['student_person_id', 'program_code']),
        'qualification': ('Qualification', ['qualification_id']),
        'placement': ('Placement', ['student_person_id', 'employer_abn', 'start_date']),
        'invoice': ('Invoice', ['invoice_no']),
        'invoice_line': ('InvoiceLine', ['invoice_no', 'line_no']),
        'payment': ('Payment', ['payment_id']),
        'person_phone': ('PhoneNumber', ['person_id', 'phone_number']),
        'subject_enrolment': ('SubjectEnrolment', ['student_person_id', 'subject_code', 'campus_code', 'term_code']),
        'result': ('Result', ['student_person_id', 'subject_code', 'campus_code', 'term_code']),
    }
    fk_cols = {'lead_staff_id', 'supervisor_person_id', 'account_no', 'agreement_id'}
    for table, (label, keys) in simple.items():
        for r in rows(table):
            n = g.merge_node(label, {k: r[k] for k in keys})
            g.set(n, **{k: (v if v != '' else None) for k, v in r.items()
                        if k not in keys and k not in fk_cols})
    # subtype IS_A hops
    for table, sub, sup, key in [('student', 'Student', 'Person', 'person_id'),
                                 ('staff', 'Staff', 'Person', 'person_id'),
                                 ('guardian', 'Guardian', 'Person', 'person_id'),
                                 ('qcaa_subject', 'QCAASubject', 'Subject', 'subject_code'),
                                 ('vet_unit', 'VETUnit', 'Subject', 'subject_code')]:
        for r in rows(table):
            g.merge_rel('IS_A', g.find(sub, **{key: r[key]}), g.find(sup, **{key: r[key]}))
    for r in rows('person_phone'):
        g.merge_rel('HAS_PHONE', g.find('Person', person_id=r['person_id']),
                    g.find('PhoneNumber', person_id=r['person_id'], phone_number=r['phone_number']))
    for r in rows('guardianship'):
        g.merge_rel('GUARDIAN_OF', g.find('Guardian', person_id=r['guardian_person_id']),
                    g.find('Student', person_id=r['student_person_id']),
                    relationship_type=r['relationship_type'], is_primary_contact=r['is_primary_contact'])
    for r in rows('staff'):
        if r['supervisor_person_id']:
            g.merge_rel('SUPERVISES', g.find('Staff', person_id=r['supervisor_person_id']),
                        g.find('Staff', person_id=r['person_id']))
    for r in rows('program_subject'):
        g.merge_rel('INCLUDES', g.find('Program', program_code=r['program_code']),
                    g.find('Subject', subject_code=r['subject_code']),
                    is_core=r['is_core'], sequence_no=r['sequence_no'])
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
    for r in rows('subject_enrolment'):
        se = g.find('SubjectEnrolment', student_person_id=r['student_person_id'], subject_code=r['subject_code'],
                    campus_code=r['campus_code'], term_code=r['term_code'])
        g.merge_rel('HAS_SUBJECT_ENROLMENT', g.find('Student', person_id=r['student_person_id']), se)
        g.merge_rel('FOR_OFFERING', se, g.find('CourseOffering', subject_code=r['subject_code'],
                                               campus_code=r['campus_code'], term_code=r['term_code']))
    for r in rows('result'):
        k = dict(student_person_id=r['student_person_id'], subject_code=r['subject_code'],
                 campus_code=r['campus_code'], term_code=r['term_code'])
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
                    start_date=r['start_date'])
        g.merge_rel('UNDERTAKES', g.find('Student', person_id=r['student_person_id']), pl)
        g.merge_rel('HOSTED_BY', pl, g.find('HostEmployer', employer_abn=r['employer_abn']))
        g.merge_rel('GOVERNED_BY', pl, g.find('PlacementAgreement', agreement_id=r['agreement_id']))
    for table, label, key in [('student', 'Student', 'person_id'), ('guardian', 'Guardian', 'person_id'),
                              ('host_employer', 'HostEmployer', 'employer_abn')]:
        for r in rows(table):
            if r['account_no']:
                g.merge_rel('HOLDS_ACCOUNT', g.find(label, **{key: r[key]}),
                            g.find('BillingAccount', account_no=r['account_no']))
    for r in rows('invoice'):
        i = g.find('Invoice', invoice_no=r['invoice_no'])
        g.merge_rel('BILLED_TO', i, g.find('BillingAccount', account_no=r['account_no']))
        g.merge_rel('RAISED_FOR', i, g.find('Student', person_id=r['student_person_id']))
        g.merge_rel('FOR_TERM', i, g.find('Term', term_code=r['term_code']))
    for r in rows('invoice_line'):
        g.merge_rel('HAS_LINE', g.find('Invoice', invoice_no=r['invoice_no']),
                    g.find('InvoiceLine', invoice_no=r['invoice_no'], line_no=r['line_no']))
    for r in rows('payment'):
        g.merge_rel('SETTLES', g.find('Payment', payment_id=r['payment_id']),
                    g.find('Invoice', invoice_no=r['invoice_no']))
    return g


if __name__ == '__main__':
    import json
    for build in (build_model_a, build_model_b):
        g = build()
        print(f"MODEL {g.name}: {len(g.nodes)} nodes, {len(g.rels)} relationships, {g.prop_count()} properties")
        print('  labels:', g.label_counts())
        print('  types :', g.type_counts())
