# Action

**Package:** `src/action/`
**Role:** Record the care the owner reports doing — the completion buttons on a
`companion` care plan, and the watering button.
**Owner:** _TBD_

## Responsibilities

- Append one event per button press in the GUI.
- Accept a watering whether or not the plant has a problem (no care plan needed).
- Deduplicate a retried press (`client_event_id`).
- Tell the GUI which steps of a care plan are done, and when the plant was last watered.

## Data it owns

- PostgreSQL schema `action`: one append-only table, `care_event`.
- MinIO: none.

### `action.care_event`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `plant_id` | uuid | `registry.plant.id`. Not a DB foreign key — checked via `registry` |
| `event_type` | text | `action_completed` \| `watered` |
| `care_plan_id` | text, nullable | `companion`'s `care_plan.id` (`cp_…`). Always set for `action_completed`; for `watered` only when pressed from a care card |
| `action_id` | text, nullable | `companion`'s `care_plan.actions[].id` (`act_…`). `action_completed` only |
| `action_type` | text, nullable | `water` \| `move` \| `inspect` \| `other` |
| `details` | json(b), nullable | Event-specific extras |
| `occurred_at` | timestamptz | When the owner did it (client clock; defaults to receipt time; ≤ now + 5 min) |
| `recorded_at` | timestamptz | When the server stored it |
| `recorded_by_user_id` / `recorded_by_device_id` | uuid, nullable | Who pressed: an owner or a planter. Exactly one is set |
| `client_event_id` | text, nullable | Unique per plant when set (partial unique index) |

- **Append-only.** Rows are never updated or deleted; state such as "last
  watered" is derived by reading the log.
- **New kinds of event** add an `event_type` value (and a request model in
  `schemas.py`); event-specific data goes in `details`, so the table keeps its shape.
- `companion`'s ids are stored as received — `companion` has no published
  interface to check them against yet.

## HTTP API (`/action`, mounted by `main_web`)

| Method & path | Caller | Purpose |
|---|---|---|
| `POST /action/plants/{plant_id}/events` | owner (`CurrentUser`) | record an event. 404 for another owner's / unknown plant, 409 for an archived plant |
| `POST /action/devices/me/events` | device (`CurrentDevice`) | record an event for the plant bound to the device. 404 if none |
| `GET /action/plants/{plant_id}/care-plans/{care_plan_id}/progress` | owner | the care plan's completed steps + the plant's `last_watered_at`. Readable for archived plants too |
| `GET /action/devices/me/care-plans/{care_plan_id}/progress` | device | same, for the plant bound to the device |

The `POST`s answer **201** with the new event, or **200** with the earlier one when
`client_event_id` was already recorded for the plant. Request body, by `type`:

```json
{"type": "action_completed", "care_plan_id": "cp_a7b8c9d0e1f2", "action_id": "act_8e4b1a2c",
 "action_type": "water", "occurred_at": "2026-09-22T08:30:00Z", "client_event_id": "…", "details": {}}
```

```json
{"type": "watered", "care_plan_id": null, "occurred_at": null, "client_event_id": "…", "details": {"amount_ml": 200}}
```

Progress lists each completed step once (its first completion), oldest first.
`action` does not know a plan's full list of steps — `companion` does — so the
client treats the `care_plan.actions[]` ids not listed as still to do.

## Published interface (in-process)

```python
from action import (
    list_care_events,  # (session, plant_id, *, since=, event_types=, limit=) -> list[CareEventRead]
    CareEventRead,
    CareEventType,     # ACTION_COMPLETED | WATERED
)

events = list_care_events(session, plant_id, since=week_ago, limit=50)
[e.model_dump(mode="json") for e in events]  # oldest first, same fields as the HTTP response
```

- `advice` reads what the owner has done for a plant (completed steps, waterings)
  before writing new advice.

## Internal design

```
src/action/
├── api.py         # /action router — access checks, status codes
├── interface.py   # the in-process interface above
├── service.py     # record_event (append + dedup), list_events, get_care_plan_progress, last_watered_at
├── schemas.py     # request union by `type`, CareEventRead, CarePlanProgress
├── models.py      # CareEvent
└── db.py          # ACTION_SCHEMA, Base (own MetaData), utcnow(), init_models()
```
