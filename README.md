# SoilSense Desktop (Tkinter + Neon PostgreSQL)

A desktop version of the SoilSense smart sugarcane advisory, written in Python with **Tkinter**.
It connects **live to the same Neon PostgreSQL database as the website**, so anything you do
here (mark advice as done, change thresholds) shows on the website too, and the other way round.

## Run it

1. Install Python 3.10+ from python.org (tick **"Add python.exe to PATH"**).
2. In this folder, open a terminal and run:
   ```
   pip install -r requirements.txt
   python main.py
   ```
3. First launch asks for the **Neon connection string** (Neon → project → **Connect**).
   It is tested, then saved in `config.ini` on this computer only.
4. Log in with the demo account: **demo@soilsense.in / Demo@1234**.

> `config.ini` holds the database password — never zip it, email it or upload it.
> To give someone else access, create a separate role in Neon (Roles → New role) and give them
> that connection string instead of yours; delete the role afterwards.

## Screens

| Screen | What it does |
|---|---|
| Login | e-mail / mobile / Farmer ID + password, checked with bcrypt against the stored hash |
| Dashboard | moisture, water, pending advice, sensors online; water-by-field and moisture-trend charts; fields table; alerts; **Re-check advice** |
| Live sensors | choose a field and period; moisture / temperature / humidity charts with threshold lines; hover read-out (BST search) |
| Analytics | water per day, fertilizer by product, yield vs district, next-season forecast, field comparison |
| Recommendations | filter by status and type; **Mark as done** (writes the irrigation/fertilizer log in the same transaction) or **Dismiss** |
| Settings | edit alert thresholds (database CHECK rules reject impossible values), then every field is re-checked |

## How the code is organised (3 layers)

```
main.py                     start the app
soilsense/
├── app.py                  window, sidebar, Back button, auto-refresh every 60 s
├── screens/                UI only — one file per screen (Tkinter + matplotlib)
├── engine.py               recommendation rules (Python port of the website engine)
├── db.py                   ALL SQL — parameterised queries, transactions
├── auth.py                 bcrypt login
├── worker.py               background thread so the window never freezes
├── config.py               reads the Neon address from config.ini / env var
└── ds/                     hand-written data structures
tests/test_ds.py            unit tests:  python -m unittest discover -s tests
```

## Data structures (written by hand, used by the app)

| Structure | File | Where it is used |
|---|---|---|
| Linked list | `ds/linked_list.py` | storage inside the queue (O(1) add at tail, remove at head) |
| Queue (FIFO) | `ds/queue.py` | `worker.py`: database jobs run in the order the screens asked; results come back the same way |
| Stack (LIFO) | `ds/stack.py` | `app.py`: screen history for the **← Back** button |
| Binary search tree | `ds/bst.py` | `screens/sensors.py`: readings keyed by time; hovering a chart does a `floor()` search for the reading at that moment (built balanced with `from_sorted`) |

Built-in structures also used: **set** (fertilizers applied recently, engine), **dict** (efficiency
table, sensor lookups), **lists** (rules append recommendations), **hashing** (bcrypt passwords).

## Database features used

Tables with primary / foreign keys, CHECK constraints, a partial unique index (one pending
advice per field and rule), triggers, the `v_sensor_status` view, B-tree indexes and
transactions — see `database/schema.sql` in the main SoilSense project.

## Performance & reliability

- **One round trip per screen.** Each screen loads everything it needs in a single query
  (`db.bundle()` combines the parts with `json_agg`), so a refresh costs one trip to Neon, not six.
- **Re-check advice for all fields in ~9 queries** — contexts for every field are loaded together and
  results are saved with one multi-row upsert, inside one transaction.
- **Never freezes:** database work runs on a background thread (`worker.py`); the window only draws.
- **Latest answer wins:** if you switch field or period quickly, older replies are ignored.
- **No pile-up:** the 60-second auto-refresh is skipped while a screen is still loading.
- **Dropped connections recover:** reads reconnect and retry once; a failed save says "nothing was
  saved" (the transaction rolls back) and the next action reconnects.
- **No memory leaks:** tested with hundreds of screen switches and 12 logout/login cycles — memory,
  Python objects, Tk widgets and Tcl callbacks all stay flat. (matplotlib's extra window-level
  callbacks are removed when each chart is created, and the mouse wheel is bound once for the app.)
