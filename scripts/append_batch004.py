"""
append_batch004.py
──────────────────
Appends arabizi_candidate_bank_batch004_intake.csv rows to the main
arabizi_candidate_bank.csv file. Idempotent — checks for existing
candidate_ids before appending.

Run:
    python scripts/append_batch004.py
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_BANK = ROOT / 'data/knowledge_base/arabizi/arabizi_candidate_bank.csv'
BATCH = ROOT / 'data/knowledge_base/arabizi/arabizi_candidate_bank_batch004_intake.csv'

def main():
    # load existing IDs
    with open(MAIN_BANK, encoding='utf-8-sig') as f:
        existing_rows = list(csv.DictReader(f))
    existing_ids = {r['candidate_id'] for r in existing_rows}
    fieldnames = list(existing_rows[0].keys())

    # load batch
    with open(BATCH, encoding='utf-8-sig') as f:
        batch_rows = list(csv.DictReader(f))

    # check for overlap
    new_rows = [r for r in batch_rows if r['candidate_id'] not in existing_ids]
    already_in = len(batch_rows) - len(new_rows)
    if already_in:
        print(f'  [WARN] {already_in} rows already in bank — skipping duplicates')

    if not new_rows:
        print('  Nothing to append — all rows already present.')
        return 0

    # append
    with open(MAIN_BANK, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        for row in new_rows:
            writer.writerow(row)

    first_id = new_rows[0]['candidate_id']
    last_id = new_rows[-1]['candidate_id']
    print(f'  Appended {len(new_rows)} rows to {MAIN_BANK.name}')
    print(f'  Bank now contains {len(existing_rows) + len(new_rows)} entries')
    print(f'  ID range added: {first_id} -> {last_id}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
