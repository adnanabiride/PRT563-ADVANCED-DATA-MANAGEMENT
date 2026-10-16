# Expected results

Produced by the independent in-memory replica of the graph (`analysis/`), which loads the same 26 CSV files with the same rules as `import.txt`. Use it to check each script after running it in Neo4j Desktop. All queries use the fixed reporting date **2026-09-14**.

Tolerances: counts, keys, names and query rows must match exactly. GDS scores may differ in the last decimal places; eigenvector scores differ more because GDS stops after 20 iterations without converging (compare rankings, not values). `PROFILE` database hits will not equal the replica's logical accesses - compare the ratio Model B / Model A, not the absolute numbers.

## 1. import.txt

After a clean run: **323 nodes, 633 relationships, 20 labels, 22 relationship types, 2384 stored property values** (Model B). `SHOW CONSTRAINTS` lists 28 uniqueness constraints; `SHOW INDEXES` lists 35 indexes: the 5 query-driven indexes, one backing index per constraint and the two built-in token-lookup indexes.

Validation (section 8):

| Statement | Expected |
|---|---|
| 8.1 nodes per label | see table below (323 nodes in total) |
| 8.2 relationships per type | see table below (633 relationships in total) |
| 8.3 rows accounted for | subject_enrolments 95, results 71 |
| 8.4 billing-account category check | no rows (every account has exactly one holder of an allowed type) |
| 8.5 SUBJECT disjoint and total | overlapping_subjects 0, unspecialised_subjects 0 |
| 8.6 PERSON total | roleless_people 0, multi_role_people 2 (Priya Raman, Meena Chandra) |
| 8.7 structural integrity (NOT NULL, cardinality) | violations = 0 |
| 8.8 second holder for ACC-1001 (commented demo) | fails with Neo.ClientError.Schema.ConstraintValidationFailed (shown as GQLSTATUS 22N79, property uniqueness constraint violated, on Neo4j 2025+) |

Nodes per label (a node can carry several labels, so the column does not add up to the node total):

| Label | Nodes |
|---|---|
| BillingAccount | 22 |
| Campus | 5 |
| CourseOffering | 32 |
| Enrolment | 26 |
| Guardian | 11 |
| HostEmployer | 8 |
| Invoice | 42 |
| InvoiceLine | 73 |
| Payment | 33 |
| Person | 42 |
| Placement | 11 |
| PlacementAgreement | 11 |
| Program | 4 |
| QCAASubject | 4 |
| Qualification | 2 |
| Staff | 10 |
| Student | 24 |
| Subject | 8 |
| Term | 4 |
| VETUnit | 4 |

Relationships per type:

| Type | Relationships |
|---|---|
| AT_CAMPUS | 58 |
| AWARDED | 2 |
| BILLED_TO | 42 |
| FOR_TERM | 42 |
| GOVERNED_BY | 11 |
| GUARDIAN_OF | 16 |
| HAS_ENROLMENT | 26 |
| HAS_LINE | 73 |
| HOLDS_ACCOUNT | 22 |
| HOSTED_BY | 11 |
| INCLUDES | 12 |
| IN_PROGRAM | 26 |
| IN_TERM | 32 |
| LEADS | 32 |
| NEXT_TERM | 3 |
| OF_SUBJECT | 32 |
| RAISED_FOR | 42 |
| REQUIRES | 3 |
| SETTLES | 33 |
| SUPERVISES | 9 |
| TOOK | 95 |
| UNDERTAKES | 11 |

Reconciliation against the relational source (`analysis/reconcile.py`): 26 tables, 600 rows, 3,143 cell-level checks, 0 mismatches.

| Source table | Rows | Checks | Mismatches | Stored in the graph as |
|---|---|---|---|---|
| campus | 5 | 35 | 0 | :Campus |
| term | 4 | 24 | 0 | :Term |
| program | 4 | 20 | 0 | :Program |
| subject | 8 | 40 | 0 | :Subject (+ label as discriminator) |
| qcaa_subject | 4 | 16 | 0 | :Subject:QCAASubject |
| vet_unit | 4 | 16 | 0 | :Subject:VETUnit |
| host_employer | 8 | 48 | 0 | :HostEmployer + HOLDS_ACCOUNT |
| billing_account | 22 | 88 | 0 | :BillingAccount |
| placement_agreement | 11 | 55 | 0 | :PlacementAgreement |
| person | 42 | 462 | 0 | :Person |
| person_phone | 27 | 54 | 0 | Person.phone_mobile / phone_home / phone_work |
| student | 24 | 144 | 0 | :Person:Student + HOLDS_ACCOUNT |
| staff | 10 | 60 | 0 | :Person:Staff + SUPERVISES |
| guardian | 11 | 33 | 0 | :Person:Guardian + HOLDS_ACCOUNT |
| course_offering | 32 | 224 | 0 | :CourseOffering + OF_SUBJECT/AT_CAMPUS/IN_TERM/LEADS |
| enrolment | 26 | 182 | 0 | :Enrolment + HAS_ENROLMENT/IN_PROGRAM/AT_CAMPUS |
| qualification | 2 | 12 | 0 | :Qualification + AWARDED |
| placement | 11 | 77 | 0 | :Placement + UNDERTAKES/HOSTED_BY/GOVERNED_BY |
| invoice | 42 | 336 | 0 | :Invoice + BILLED_TO/RAISED_FOR/FOR_TERM |
| invoice_line | 73 | 292 | 0 | :InvoiceLine + HAS_LINE |
| payment | 33 | 198 | 0 | :Payment + SETTLES |
| guardianship | 16 | 48 | 0 | [:GUARDIAN_OF {relationship_type, is_primary_contact}] |
| program_subject | 12 | 36 | 0 | [:INCLUDES {is_core, sequence_no}] |
| subject_prerequisite | 3 | 3 | 0 | [:REQUIRES] |
| subject_enrolment | 95 | 285 | 0 | [:TOOK {enrolled_on, status}] |
| result | 71 | 355 | 0 | folded onto [:TOOK] {result_type, grade_letter, competency_outcome, awarded_date} |

## 2. queries.txt

### Q1 - assessment conflict of interest

| staff_member | dependant | finding | subject | campus | term | action | eligible_assessors |
|---|---|---|---|---|---|---|---|
| Priya Raman | Ethan Brady | CONFLICT | SUB-0004 | RDLD | 2026T3 | Not yet assessed - reassign assessor now | Meena Chandra |
| Meena Chandra | Aarav Chandra | No conflict |  |  |  |  | [] |

### Q2 - blue card compliance sweep (next term 2026T4)

| staff_member | blue_card_expiry | days_remaining | risk | rostered | students_affected | escalation | contact |
|---|---|---|---|---|---|---|---|
| Meena Chandra | 2026-09-30 | 16 | BLOCKER - lapses before 2026T4 starts | SUB-0004@CBLT, SUB-0008@RDLD | 3 | Meena > Tom > Grace | tom.ellery@tis.qld.edu.au |
| Sarah McKenzie | 2026-11-28 | 75 | BLOCKER - lapses during 2026T4 | SUB-0006@CBLT | 3 | Sarah > Tom > Grace | tom.ellery@tis.qld.edu.au |
| Daniel Okonjo | 2026-10-15 | 31 | RENEW - not rostered in 2026T4 | [] | 0 | Daniel > Tom > Grace | tom.ellery@tis.qld.edu.au |
| Nadia Petrosyan | 2026-12-05 | 82 | RENEW - not rostered in 2026T4 | [] | 0 | Nadia > Tom > Grace | tom.ellery@tis.qld.edu.au |

### Q3 - campus debt against the school-wide average

| campus | open_invoices | debtors | balance_owing | variance_vs_average | pct_over_90_days | flag |
|---|---|---|---|---|---|---|
| Caboolture Campus | 7 | 4 | 5420.00 | +2867.00 | 92.4 | ABOVE AVERAGE - escalate |
| Ipswich Campus | 4 | 2 | 3145.00 | +592.00 | 100.0 | ABOVE AVERAGE - escalate |
| Redlands Campus | 5 | 3 | 2205.00 | -348.00 | 69.2 | within average |
| Eagle Farm Campus | 4 | 3 | 1740.00 | -813.00 | 100.0 | within average |
| Toowoomba Campus | 1 | 1 | 255.00 | -2298.00 | 100.0 | within average |

School-wide average: **2553.00** over all five campuses. The same figure comes from the corrected SQL query in `a2_feedback_fixes.sql` (FIX 1).

### Q4 - prerequisite breaches and their root cause

| student_no | program | subject | term | unmet_prerequisite | prereq_history | root_cause |
|---|---|---|---|---|---|---|
| S2026007 | PRG101 | SUB-0008 | 2026T3 | SUB-0001 | 2026T1 D | Enrolled outside program |
| S2026001 | PRG102 | SUB-0007 | 2026T4 | SUB-0002 | never attempted | Enrolled outside program |
| S2026005 | PRG103 | SUB-0004 | 2026T3 | SUB-0005 | never attempted | Enrolled outside program |
| S2026003 | PRG104 | SUB-0004 | 2026T3 | SUB-0005 | never attempted | Enrolled outside program |
| S2026014 | PRG104 | SUB-0004 | 2026T3 | SUB-0005 | never attempted | Enrolled outside program |
| S2026001 | PRG102 | SUB-0004 | 2026T3 | SUB-0005 | never attempted | Program design gap |
| S2026011 | PRG102 | SUB-0004 | 2026T3 | SUB-0005 | never attempted | Program design gap |
| S2026017 | PRG102 | SUB-0004 | 2026T3 | SUB-0005 | never attempted | Program design gap |
| S2026020 | PRG101 | SUB-0004 | 2026T4 | SUB-0005 | 2026T3 NYC | Progression control failure |
| S2026014 | PRG104 | SUB-0008 | 2026T2 | SUB-0001 | 2026T1 D | Progression control failure |

10 rows for 8 students: 5 x Enrolled outside program, 3 x Program design gap, 2 x Progression control failure.

## 3. Modelling experiment (supplementary/experiment_profile.txt)

Logical accesses (label-scan nodes + index seeks + relationship expansions + property reads) per query; W1 and W2 are averaged over all 24 students and 22 accounts.

| Variant | Q1 | Q2 | Q3 | Q4 | W1 | W2 | Workload |
|---|---|---|---|---|---|---|---|
| A (baseline) | 98 | 194 | 392 | 1034 | 39 | 20 | 1777 |
| B (optimised) | 62 | 176 | 264 | 827 | 31 | 14 | 1374 |
| B - labels | 90 | 188 | 264 | 837 | 33 | 15 | 1427 |
| B - fold | 70 | 182 | 264 | 1024 | 37 | 14 | 1591 |
| B - pivot | 62 | 168 | 264 | 827 | 32 | 15 | 1368 |
| B - materialise | 62 | 176 | 392 | 827 | 31 | 18 | 1506 |
| B - next_term | 62 | 184 | 264 | 827 | 31 | 14 | 1382 |
| B - typed | 62 | 176 | 264 | 827 | 31 | 14 | 1374 |

Every variant returns identical rows for all six queries.

## 4. gds_centrality.txt

C1 projection: nodeCount **65**, relationshipCount **272** (136 undirected relationships stored in both directions).

C3 iterations: PageRank ranIterations 20, didConverge false; ArticleRank 19, true; eigenvector 20, false. C4: GDS converges after 227 iterations (Neo4j run, 14 October 2026); the replica's stricter per-node tolerance needs about 622.

| Staff member | Degree | PageRank | ArticleRank | Eigenvector | Betweenness | Closeness | Harmonic | G1 efficiency loss | G2 students taught |
|---|---|---|---|---|---|---|---|---|---|
| Tom Ellery | 9.0 | 1.994 | 0.389 | 0.222 | 855.4 | 0.441 | 0.503 | 0.1211 | 4 |
| Fatima Al-Hassan | 7.0 | 1.429 | 0.332 | 0.263 | 392.4 | 0.374 | 0.443 | 0.0432 | 13 |
| Priya Raman | 7.0 | 1.505 | 0.336 | 0.153 | 383.7 | 0.368 | 0.434 | 0.0475 | 11 |
| Daniel Okonjo | 6.0 | 1.302 | 0.307 | 0.117 | 343.5 | 0.354 | 0.414 | 0.0343 | 7 |
| Sarah McKenzie | 7.0 | 1.424 | 0.331 | 0.249 | 329.8 | 0.381 | 0.448 | 0.0369 | 14 |
| Grace Whitlam | 3.0 | 0.766 | 0.228 | 0.082 | 234.5 | 0.364 | 0.398 | 0.0278 | 0 |
| Beau Larsen | 3.0 | 0.803 | 0.230 | 0.062 | 192.2 | 0.330 | 0.370 | 0.0199 | 4 |
| Angus Fraser | 3.0 | 0.880 | 0.232 | 0.019 | 134.5 | 0.278 | 0.316 | 0.0070 | 2 |
| Nadia Petrosyan | 3.0 | 0.903 | 0.231 | 0.057 | 127.7 | 0.320 | 0.359 | 0.0301 | 2 |
| Meena Chandra | 3.0 | 0.790 | 0.230 | 0.068 | 96.8 | 0.323 | 0.363 | 0.0118 | 3 |

Evaluation against the ground truth (Section 6 of the report):

| Algorithm | rho all nodes (G1) | 95% CI | rho staff (G1) | precision@3 staff (G1) | rho staff (G2) | Kendall tau, 10% TOOK removed (mean +/- SD) |
|---|---|---|---|---|---|---|
| Degree | 0.41 | 0.16-0.63 | 0.92 | 0.67 | 0.75 | 0.996 +/- 0.013 |
| PageRank | 0.29 | 0.02-0.53 | 0.89 | 1.00 | 0.69 | 0.927 +/- 0.053 |
| ArticleRank | 0.32 | 0.05-0.56 | 0.83 | 1.00 | 0.67 | 0.961 +/- 0.044 |
| Eigenvector | 0.49 | 0.25-0.70 | 0.82 | 0.67 | 0.79 | 0.928 +/- 0.059 |
| Betweenness | 0.93 | 0.86-0.96 | 0.88 | 1.00 | 0.61 | 0.951 +/- 0.047 |
| Closeness | 0.93 | 0.86-0.97 | 0.85 | 0.67 | 0.65 | 0.968 +/- 0.035 |
| Harmonic | 0.90 | 0.80-0.97 | 0.88 | 0.67 | 0.72 | 0.988 +/- 0.023 |

## 5. gds_similarity.txt

Placed students (leave-one-out cases): 11; unplaced students: 13. S0 profiles 24 students; S2 projects 32 nodes and 94 relationships; S3 55 nodes and 94 relationships; S4 24 nodes.

S5 and S6 list three peers per student. Scores must match; the peers themselves can differ where scores tie (GDS breaks ties its own way, which is the instability measured below), and GDS KNN is approximate, so a top-3 list can miss a near neighbour (in the Neo4j run, Priya Raman was given Malik Traore 0.183 instead of Samuel Otieno 0.187). S9 asks KNN for all 23 neighbours, so its recommendations are exact.

| Variant | same program in top 3 | same campus in top 3 | students with a tied 3rd/4th peer |
|---|---|---|---|
| NS Jaccard (subject) | 0.26 | 0.21 | 0.83 |
| NS Overlap (subject) | 0.29 | 0.22 | 0.83 |
| NS Cosine (subject) | 0.26 | 0.21 | 0.83 |
| NS Jaccard (class) | 0.28 | 0.86 | 0.33 |
| NS Overlap (class) | 0.32 | 0.86 | 0.46 |
| NS Cosine (class) | 0.31 | 0.86 | 0.50 |
| KNN Cosine (profile) | 0.35 | 0.19 | 0.00 |
| KNN Pearson (profile) | 0.32 | 0.19 | 0.00 |
| KNN Euclidean (profile) | 0.29 | 0.21 | 0.17 |
| Random baseline | 0.22 | 0.19 | - |

Leave-one-out placement matching (k = 3 peers):

| Variant | Mode | Hit@1 | Hit@3 | MRR |
|---|---|---|---|---|
| NS Jaccard (subject) | similarity only | 0.09 | 0.55 | 0.30 |
| NS Jaccard (subject) | within program | 0.27 | 0.82 | 0.53 |
| NS Overlap (subject) | similarity only | 0.09 | 0.64 | 0.33 |
| NS Overlap (subject) | within program | 0.27 | 0.82 | 0.53 |
| NS Cosine (subject) | similarity only | 0.09 | 0.55 | 0.30 |
| NS Cosine (subject) | within program | 0.27 | 0.82 | 0.53 |
| NS Jaccard (class) | similarity only | 0.09 | 0.18 | 0.14 |
| NS Jaccard (class) | within program | 0.36 | 0.82 | 0.59 |
| NS Overlap (class) | similarity only | 0.09 | 0.18 | 0.14 |
| NS Overlap (class) | within program | 0.36 | 0.82 | 0.59 |
| NS Cosine (class) | similarity only | 0.09 | 0.18 | 0.14 |
| NS Cosine (class) | within program | 0.36 | 0.82 | 0.59 |
| KNN Cosine (profile) | similarity only | 0.09 | 0.55 | 0.30 |
| KNN Cosine (profile) | within program | 0.36 | 0.82 | 0.56 |
| KNN Pearson (profile) | similarity only | 0.09 | 0.64 | 0.35 |
| KNN Pearson (profile) | within program | 0.36 | 0.82 | 0.56 |
| KNN Euclidean (profile) | similarity only | 0.18 | 0.55 | 0.35 |
| KNN Euclidean (profile) | within program | 0.45 | 0.82 | 0.61 |
| Random (expected) | baseline | 0.17 | 0.50 | 0.41 |
| Popularity | baseline | 0.27 | 0.27 | 0.38 |
| Program rule | baseline | 0.45 | 0.82 | 0.64 |

S9 recommendations for the unplaced students (program filter, KNN Euclidean on the performance profile; S10 lists the cold-start students):

| Student | Program | Campus | Recommended host | Score | Most similar placed peers |
|---|---|---|---|---|---|
| Tali Nguyen | PRG102 | EGLF | Redlands Office Solutions | 0.284 | Sienna Marsh (0.161), Priya Raman (0.123) |
| Ethan Brady | PRG103 | RDLD | NO PEER IN PROGRAM - cold start |  |  |
| Amara Nkemelu | PRG102 | RDLD | Redlands Office Solutions | 0.229 | Priya Raman (0.115), Sienna Marsh (0.114) |
| Lucas Hartley | PRG101 | CBLT | Moreton Trade Services | 0.411 | Willow Reid (0.333), Malik Traore (0.211), Bilal Haddad (0.200) |
| Noah Petrov | PRG103 | RDLD | NO PEER IN PROGRAM - cold start |  |  |
| Ruby Tanaka | PRG102 | EGLF | Redlands Office Solutions | 0.253 | Sienna Marsh (0.130), Priya Raman (0.123) |
| Oscar Delaney | PRG104 | IPSW | Moreton Bay Childcare | 0.272 | Zara Ahmadi (0.140), Mia Fletcher (0.132), Freya Lindqvist (0.114) |
| Hunter Kelly | PRG103 | IPSW | NO PEER IN PROGRAM - cold start |  |  |
| Isla Moreau | PRG102 | RDLD | Redlands Office Solutions | 0.284 | Sienna Marsh (0.161), Priya Raman (0.123) |
| Diego Salazar | PRG103 | RDLD | NO PEER IN PROGRAM - cold start |  |  |
| Chloe Barrett | PRG102 | CBLT | Redlands Office Solutions | 0.257 | Priya Raman (0.140), Sienna Marsh (0.118) |
| Aarav Chandra | PRG103 | CBLT | NO PEER IN PROGRAM - cold start |  |  |
| Samuel Otieno | PRG104 | TWMB | Moreton Bay Childcare | 0.297 | Freya Lindqvist (0.224), Zara Ahmadi (0.159), Mia Fletcher (0.138) |
