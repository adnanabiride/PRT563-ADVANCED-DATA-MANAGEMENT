PRT563 Advanced Data Management - Assessment 4
Group 2: The Industry School database in Neo4j

Group members
  Cynthia Ebele Ikegbunam (group leader)
  Md Adnan Abir
  Chepngenoh S Chepkwony
  Najmus Sakeeb

What this is
------------
In Assessment 2 we built a SQLite database for The Industry School (26 tables,
600 rows). For this assessment we moved it into Neo4j, wrote four Cypher query
use cases, and ran two Graph Data Science (GDS) analyses on it. Our report is
submitted on Learnline as a Word document. Every script the report talks about
is in this repository.

We ran everything on 14 October 2026 using Neo4j Desktop 2.2.1 (Neo4j 2026.09.0,
Cypher 25) with GDS 2026.09.0. All the results matched what we expected (see
supplementary/EXPECTED_RESULTS.md), and the screenshots are in
supplementary/run_evidence/. The scripts should also work on Neo4j 5.9 or newer
with GDS 2.x.

Files
-----
import.txt
    Task 2. Creates the constraints and indexes, loads all the CSV files with
    LOAD CSV, builds the derived parts (NEXT_TERM and invoice balances) and
    checks the result (sections 1 to 8).

queries.txt
    Task 3. Our four query use cases, Q1 to Q4. Each one starts with the
    scenario and who would use it.

gds_centrality.txt
    Task 4. Key-person risk. Seven centrality algorithms (statements C0 to C10).

gds_similarity.txt
    Task 5. Work placement matching. NodeSimilarity and KNN versions
    (statements S0 to S11).

csv/
    The 26 CSV files, one for each table. Each has a header row, and an empty
    field means NULL in the SQL database.

figures/
    The figures from the report. figure2_graph_model.svg is the full-size graph
    data model for Task 1.
    PRT563_All_Figures_Colab.ipynb redraws every figure except Figure 4 (that
    one is a Neo4j screenshot) as SVG and PNG. Open it in Google Colab and
    click Runtime > Run all.
    make_all_figures.py redraws only the diagrams. To use it on your own
    computer: pip install pillow cairosvg, then python make_all_figures.py

supplementary/EXPECTED_RESULTS.md
    What each script should return when it runs correctly.

supplementary/run_evidence/
    Screenshots of every script we ran in Neo4j, plus a checklist comparing
    them with the expected results.

supplementary/import_baseline.txt and queries_baseline.txt
    Model A, the simple rule-based version of the graph. Section 4 of the
    report compares our final model against it.

supplementary/experiment_profile.txt and experiment_results_template.csv
    The same workload run with PROFILE, and a sheet for writing down the
    database hits.

supplementary/a2_feedback_fixes.sql
    Fixes from the Assessment 2 feedback: the corrected debt query, and the
    billing account rule enforced with UNIQUE indexes and triggers.

supplementary/A2_revised_UML.svg and .png
    The UML class diagram from Assessment 2, revised after feedback.

supplementary/analysis/
    The Python code we used to check the migration cell by cell, run the
    modelling experiment and evaluate the algorithms.

supplementary/DECISIONS.md
    Our log of design decisions.

supplementary/trello/
    How we organised our Trello board.

How to run it in Neo4j Desktop
------------------------------
1. Create a local instance with Neo4j 5.9 or newer. (Q4 uses the ->+ pattern,
   which needs 5.9, and the relationship property uniqueness constraint needs
   5.7.) Install the Graph Data Science plugin and start the instance.

2. Open the instance folder (... > Open folder > Import) and copy all the files
   from csv/ into it. Copy the files themselves, not the csv folder, because
   import.txt reads them as file:///campus.csv and so on.

3. Run import.txt. You can use cypher-shell:
       cypher-shell -u neo4j -p <password> -f import.txt
   or run it one statement at a time in Neo4j Browser (turn on the
   multi-statement query editor in the Browser settings). Section 8 checks the
   import; compare it with section 1 of EXPECTED_RESULTS.md. Statement 8.8 is
   commented out on purpose. Run it by itself and you will see the constraint
   reject a second holder for the same account.

4. Run queries.txt (Q1 to Q4) and compare with section 2 of
   EXPECTED_RESULTS.md. The queries use a fixed date, 2026-09-14, so you
   should get the same results we did.

5. Run gds_centrality.txt and then gds_similarity.txt, and compare with
   sections 4 and 5. Both scripts drop their own in-memory graphs first, so
   you can run them again without errors.

6. Optional (the modelling experiment): create a second instance, copy the CSV
   files into its import folder and run supplementary/import_baseline.txt
   there. Run PART A of supplementary/experiment_profile.txt on that instance
   and PART B on the first one, then write the database hits into
   experiment_results_template.csv.

Everything uses Community Edition features only. Property existence and node
key constraints need Enterprise Edition, so we check the NOT NULL and
cardinality rules with validation query 8.7 instead.

Re-running our analysis in Python (3.10 or newer)
-------------------------------------------------
    pip install -r supplementary/analysis/requirements.txt
    cd supplementary/analysis
    python reconcile.py          (3,143 cell-level checks against the CSV rows)
    python experiment.py         (Model A, Model B and the five ablations)
    cd gds
    python centrality.py         (seven algorithms against the ground truth,
                                  takes about a minute)
    python similarity.py         (nine similarity variants, leave-one-out
                                  test, recommendations)
    cd ..
    python make_expected.py ../EXPECTED_RESULTS.md

The Python version builds both graph models from the same CSV files using the
same rules as import.txt and import_baseline.txt. For each query it counts the
logical accesses: label scans, index seeks, relationship expansions and
property reads.
