# Action

**Package:** `src/action/`
**Role:** Record the care the owner reports doing — the completion buttons on a
`companion` care plan, and the watering button.
**Owner:** _TBD_

## Responsibilities

- Append one event per button press in the GUI.
- Accept a watering whether or not the plant has a problem (no care plan needed).
- Deduplicate a retried press (`client_event_id`).

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

Both answer **201** with the new event, or **200** with the earlier one when
`client_event_id` was already recorded for the plant. Request body, by `type`:

```json
{"type": "action_completed", "care_plan_id": "cp_a7b8c9d0e1f2", "action_id": "act_8e4b1a2c",
 "action_type": "water", "occurred_at": "2026-09-22T08:30:00Z", "client_event_id": "…", "details": {}}
```

```json
{"type": "watered", "care_plan_id": null, "occurred_at": null, "client_event_id": "…", "details": {"amount_ml": 200}}
```

## Internal design

```
src/action/
├── api.py         # /action router — access checks, status codes
├── service.py     # record_event (append + dedup)
├── schemas.py     # request union by `type`, CareEventRead
├── models.py      # CareEvent
└── db.py          # ACTION_SCHEMA, Base (own MetaData), utcnow(), init_models()
```
