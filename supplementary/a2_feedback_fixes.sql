/* ==========================================================================
   PRT563 — Assignment 2 feedback fixes, carried into Assignment 4
   Group 2 · The Industry School
   ========================================================================== */

/* --------------------------------------------------------------------------
   FIX 1 — Debt query: include zero-debt campuses in the school-wide average
   --------------------------------------------------------------------------
   The marked version built its average only from campuses that already
   carried debt. A campus owing nothing was excluded from the denominator,
   which inflates the average and makes the HAVING threshold too generous.

   The corrected version drives the average from CAMPUS with LEFT OUTER JOINs,
   so every campus contributes a figure - zero if it owes nothing.
   -------------------------------------------------------------------------- */
SELECT c.campus_name,
       COUNT(DISTINCT ib.invoice_no)         AS unsettled_invoices,
       COUNT(DISTINCT ib.student_person_id)  AS students_affected,
       ROUND(SUM(ib.balance_owing), 2)       AS campus_balance_owing,
       ROUND(AVG(ib.balance_owing), 2)       AS avg_balance_per_invoice
FROM   V_INVOICE_BALANCE ib
INNER  JOIN ENROLMENT en ON ib.student_person_id = en.student_person_id
                        AND en.enrolment_status  = 'ACTIVE'
INNER  JOIN CAMPUS    c  ON en.campus_code       = c.campus_code
WHERE  ib.balance_owing > 0
GROUP  BY c.campus_name
HAVING SUM(ib.balance_owing) > (
           /* Every campus counts, including those owing nothing.
              CAMPUS drives the query; LEFT OUTER JOIN keeps debt-free
              campuses in, and COALESCE scores them zero rather than NULL. */
           SELECT AVG(campus_totals.per_campus_total)
           FROM ( SELECT c2.campus_code,
                         COALESCE(SUM(CASE WHEN ib2.balance_owing > 0
                                           THEN ib2.balance_owing END), 0)
                                AS per_campus_total
                  FROM   CAMPUS c2
                  LEFT   OUTER JOIN ENROLMENT en2
                         ON  en2.campus_code     = c2.campus_code
                         AND en2.enrolment_status = 'ACTIVE'
                  LEFT   OUTER JOIN V_INVOICE_BALANCE ib2
                         ON  ib2.student_person_id = en2.student_person_id
                  GROUP  BY c2.campus_code ) AS campus_totals
       )
ORDER  BY campus_balance_owing DESC;


/* --------------------------------------------------------------------------
   FIX 2 — Enforce BILLING_ACCOUNT category membership
   --------------------------------------------------------------------------
   BILLING_ACCOUNT is an EER categorisation: a subset of the UNION of STUDENT,
   GUARDIAN and HOST_EMPLOYER. By definition each member of a category belongs
   to exactly ONE of its superclasses (Elmasri & Navathe, 2016). The mapping
   (a nullable account_no FK in each superclass) cannot express that:

     (a) nothing stopped one account_no appearing in two superclass tables
         (a student AND a guardian holding the same account), and
     (b) nothing stopped two rows of the SAME table sharing an account_no,
         because account_no carried only a plain (non-unique) index.

   "Partial" refers to the superclasses: most students, guardians and
   employers hold no account, so account_no stays nullable.

   SQLite has no CREATE ASSERTION, so:
     - a UNIQUE index per superclass fixes (b)  (SQLite allows many NULLs), and
     - one trigger pair per superclass (INSERT and UPDATE) fixes (a).
   The Neo4j model enforces the same rule with ONE declarative constraint
   (see import.txt, constraint holds_account_unique).
   -------------------------------------------------------------------------- */

DROP INDEX IF EXISTS UX_STUDENT_ACCOUNT;
DROP INDEX IF EXISTS UX_GUARDIAN_ACCOUNT;
DROP INDEX IF EXISTS UX_HOST_EMPLOYER_ACCOUNT;
CREATE UNIQUE INDEX UX_STUDENT_ACCOUNT       ON STUDENT (account_no);
CREATE UNIQUE INDEX UX_GUARDIAN_ACCOUNT      ON GUARDIAN (account_no);
CREATE UNIQUE INDEX UX_HOST_EMPLOYER_ACCOUNT ON HOST_EMPLOYER (account_no);

DROP TRIGGER IF EXISTS trg_student_account_union_ins;
DROP TRIGGER IF EXISTS trg_student_account_union_upd;
DROP TRIGGER IF EXISTS trg_guardian_account_union_ins;
DROP TRIGGER IF EXISTS trg_guardian_account_union_upd;
DROP TRIGGER IF EXISTS trg_employer_account_union_ins;
DROP TRIGGER IF EXISTS trg_employer_account_union_upd;

CREATE TRIGGER trg_student_account_union_ins
BEFORE INSERT ON STUDENT
WHEN NEW.account_no IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Category violation: billing account already held by a guardian or employer')
    WHERE EXISTS (SELECT 1 FROM GUARDIAN      WHERE account_no = NEW.account_no)
       OR EXISTS (SELECT 1 FROM HOST_EMPLOYER WHERE account_no = NEW.account_no);
END;

CREATE TRIGGER trg_student_account_union_upd
BEFORE UPDATE OF account_no ON STUDENT
WHEN NEW.account_no IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Category violation: billing account already held by a guardian or employer')
    WHERE EXISTS (SELECT 1 FROM GUARDIAN      WHERE account_no = NEW.account_no)
       OR EXISTS (SELECT 1 FROM HOST_EMPLOYER WHERE account_no = NEW.account_no);
END;

CREATE TRIGGER trg_guardian_account_union_ins
BEFORE INSERT ON GUARDIAN
WHEN NEW.account_no IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Category violation: billing account already held by a student or employer')
    WHERE EXISTS (SELECT 1 FROM STUDENT       WHERE account_no = NEW.account_no)
       OR EXISTS (SELECT 1 FROM HOST_EMPLOYER WHERE account_no = NEW.account_no);
END;

CREATE TRIGGER trg_guardian_account_union_upd
BEFORE UPDATE OF account_no ON GUARDIAN
WHEN NEW.account_no IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Category violation: billing account already held by a student or employer')
    WHERE EXISTS (SELECT 1 FROM STUDENT       WHERE account_no = NEW.account_no)
       OR EXISTS (SELECT 1 FROM HOST_EMPLOYER WHERE account_no = NEW.account_no);
END;

CREATE TRIGGER trg_employer_account_union_ins
BEFORE INSERT ON HOST_EMPLOYER
WHEN NEW.account_no IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Category violation: billing account already held by a student or guardian')
    WHERE EXISTS (SELECT 1 FROM STUDENT  WHERE account_no = NEW.account_no)
       OR EXISTS (SELECT 1 FROM GUARDIAN WHERE account_no = NEW.account_no);
END;

CREATE TRIGGER trg_employer_account_union_upd
BEFORE UPDATE OF account_no ON HOST_EMPLOYER
WHEN NEW.account_no IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Category violation: billing account already held by a student or guardian')
    WHERE EXISTS (SELECT 1 FROM STUDENT  WHERE account_no = NEW.account_no)
       OR EXISTS (SELECT 1 FROM GUARDIAN WHERE account_no = NEW.account_no);
END;

/* --------------------------------------------------------------------------
   Verification: the union rule now holds, and can be demonstrated.
   -------------------------------------------------------------------------- */

-- Should return no rows: no account held by two superclasses at once.
SELECT account_no, COUNT(*) AS holders
FROM ( SELECT account_no FROM STUDENT       WHERE account_no IS NOT NULL
       UNION ALL
       SELECT account_no FROM GUARDIAN      WHERE account_no IS NOT NULL
       UNION ALL
       SELECT account_no FROM HOST_EMPLOYER WHERE account_no IS NOT NULL )
GROUP BY account_no
HAVING COUNT(*) > 1;
