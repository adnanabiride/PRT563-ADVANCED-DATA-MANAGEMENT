# Project board (Trello)

The work was organised on one shared Trello board. This folder documents its structure so the set-up can be
reproduced; **add the board export here before submission** (Trello: board menu › *Print, export and share* ›
*Export as JSON*, saved as `trello_board_export.json`).

## Lists

`Backlog` › `Task 1 – Graph model` › `Task 2 – Import` › `Task 3 – Queries` › `Task 4 – Centrality` ›
`Task 5 – Similarity` › `Report` › `Review` › `Done`

## Labels

`Task 1`–`Task 5`, `Report`, `A2 feedback`, `Blocked`, `Needs review`.

## Card template

- **Title:** deliverable in the imperative (e.g. "Write Q2 blue card sweep").
- **Owner** (member), **due date**, task label.
- **Checklist:** *draft* · *runs in Neo4j Desktop* · *matches EXPECTED_RESULTS.md* · *reviewed by a second member*
  · *linked in the report*.
- **Attachment / link:** the file in this repository.

## Automation (Butler rules)

1. When all checklist items on a card are complete, move the card to `Review` and add the `Needs review` label.
2. When a card is moved to `Done`, remove the `Needs review` label and mark the due date complete.
3. Every Monday, create a *Weekly review* card in `Review` with the checklist *progress · blockers · decisions*;
   decisions are copied into `supplementary/DECISIONS.md`.
4. Two days before a card's due date, notify its owner if the card is not in `Review` or `Done`.

## Cards

See `trello_cards.csv` for the task cards, owners and checklists as planned in the report's Individual
Contributions section.
