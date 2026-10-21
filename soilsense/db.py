"""
Data-access layer — every SQL query in the app lives in this file.

* PostgreSQL (Neon) through psycopg2.
* Parameterised queries only (%s placeholders), so user input can never change the SQL.
* Changes that must happen together run inside one transaction (`with transaction() as cur:`).
The screens never write SQL; they call these functions through the background worker.
"""
import json
import threading
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from . import config

_conn = None
_url = None                      # last address used (set by the first-launch screen before config.ini exists)
_lock = threading.Lock()


class DatabaseError(Exception):
    """A friendly error the screens can show."""


class ConnectionLost(DatabaseError):
    """The connection dropped (Wi-Fi blip, Neon put the idle database to sleep)."""


def connect(url=None):
    """Open (or reuse) the connection. Neon needs sslmode=require, which is in its URL."""
    global _conn, _url
    if url and url != _url:
        close()
        _url = url
    url = url or _url or config.database_url()
    if not url:
        raise DatabaseError("No database address configured.")
    with _lock:
        if _conn is None or _conn.closed:
            try:
                _conn = psycopg2.connect(
                    url, connect_timeout=15, application_name="soilsense-desktop",
                    keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3)
            except psycopg2.OperationalError as e:
                raise DatabaseError(f"Could not reach the database: {str(e).strip().splitlines()[0]}") from e
    return _conn


def close():
    global _conn
    with _lock:
        if _conn is not None and not _conn.closed:
            _conn.close()
        _conn = None


@contextmanager
def transaction():
    """All statements inside commit together, or roll back together on any error."""
    conn = connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        close()                      # dropped connection → a fresh one is opened next time
        raise ConnectionLost("Lost the connection to the database — nothing was saved. "
                             "Check your internet and try again.") from e
    except Exception:
        conn.rollback()
        raise


def rows(sql, params=()):
    """Read query. If Neon dropped an idle connection, reconnect and retry once (safe: it only reads)."""
    for attempt in (1, 2):
        try:
            with transaction() as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        except ConnectionLost:
            if attempt == 2:
                raise


def one(sql, params=()):
    r = rows(sql, params)
    return r[0] if r else None


def ping():
    return one("select now() as now, current_database() as db, version() as version")


# --------------------------------------------------------------------------- auth
def farmer_for_login(identifier):
    """Find a farmer by e-mail, Farmer ID or mobile number (password hash included)."""
    ident = identifier.strip().lower()
    digits = "".join(ch for ch in identifier if ch.isdigit())[-10:]
    return one(
        """select farmer_id, name, email, phone, village, district, state, password_hash
             from farmers
            where lower(email) = %s or lower(farmer_id) = %s or (%s <> '' and phone = %s)
            limit 1""",
        (ident, ident, digits, digits))


# --------------------------------------------------------------------------- round-trip bundling
# Every trip to Neon costs ~100–300 ms, so screens ask for everything they need in ONE query:
#   select (select json_agg(t) from (<query 1>) t) as a, (select json_agg(t) from (<query 2>) t) as b, ...
# Each part below is a (sql, params) pair; bundle() glues them together and turns the JSON back
# into Python values (dates and timestamps included).
_DATE_KEYS = {"day"}
_TIME_KEYS = {"t", "timestamp", "last_reading_at", "last_update", "resolved_at", "created_at", "updated_at"}


def _revive(value):
    from datetime import date, datetime
    if isinstance(value, list):
        return [_revive(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(v, str) and k in _DATE_KEYS:
                v = date.fromisoformat(v[:10])
            elif isinstance(v, str) and k in _TIME_KEYS:
                v = datetime.fromisoformat(v)
            elif isinstance(v, (dict, list)):
                v = _revive(v)
            out[k] = v
        return out
    return value


def bundle(**parts):
    sel = ", ".join(f"(select coalesce(json_agg(bundle_row), '[]'::json) from ({sql}) bundle_row) as {key}"
                    for key, (sql, _) in parts.items())
    params = [p for sql, ps in parts.values() for p in ps]
    r = one("select " + sel, params)
    return {k: _revive(v) for k, v in r.items()}


# --------------------------------------------------------------------------- query parts
def q_summary(fid):
    return ("""with s as (
             select count(*)::int as total,
                    count(*) filter (where health = 'ONLINE')::int as online,
                    count(*) filter (where health in ('STALE','NO_DATA'))::int as needs_check,
                    round(avg(last_reading) filter (where sensor_type = 'SOIL_MOISTURE' and health = 'ONLINE'), 1) as avg_soil_moisture,
                    max(last_reading_at) as last_update
               from v_sensor_status v join fields f using (field_id) where f.farmer_id = %s),
           w as (
             select coalesce(sum(water_amount) filter (where l."timestamp" > now() - interval '7 days'), 0) as litres_7d,
                    count(*) filter (where l."timestamp" > now() - interval '7 days')::int as sessions_7d,
                    coalesce(sum(water_amount) filter (where l."timestamp" <= now() - interval '7 days'), 0) as litres_prev_7d
               from irrigation_logs l join fields f using (field_id)
              where f.farmer_id = %s and l."timestamp" > now() - interval '14 days'),
           p as (
             select count(*)::int as pending, count(*) filter (where r.priority in ('CRITICAL','HIGH'))::int as urgent
               from recommendations r join fields f using (field_id)
              where f.farmer_id = %s and r.status = 'PENDING'),
           m as (
             select round(avg(r.value), 1) as moisture_24h_ago
               from sensor_readings r join sensors s2 using (sensor_id) join fields f using (field_id)
              where f.farmer_id = %s and s2.sensor_type = 'SOIL_MOISTURE' and r.status = 'GOOD'
                and r."timestamp" between now() - interval '27 hours' and now() - interval '21 hours')
         select s.*, w.*, p.*, m.* from s, w, p, m""", [fid] * 4)


def q_fields(fid):
    return ("""select f.field_id, f.field_name, f.area_acres, f.soil_type, f.irrigation_method,
                      sm.last_reading as soil_moisture,
                      (select count(*)::int from recommendations rc where rc.field_id = f.field_id and rc.status = 'PENDING') as pending,
                      (select count(*)::int from v_sensor_status v where v.field_id = f.field_id and v.health <> 'ONLINE') as sensors_unhealthy
                 from fields f
                 left join lateral (select last_reading from sensors
                                     where field_id = f.field_id and sensor_type = 'SOIL_MOISTURE'
                                     order by sensor_id limit 1) sm on true
                where f.farmer_id = %s
                order by f.field_id""", [fid])


def q_alerts(fid, limit=8):
    return ("""select r.rec_id, r.field_id, f.field_name, r.type, r.priority, r.action, r."timestamp"
                 from recommendations r join fields f using (field_id)
                where f.farmer_id = %s and r.status = 'PENDING' and (r.priority in ('CRITICAL','HIGH') or r.type = 'ALERT')
                order by case r.priority when 'CRITICAL' then 0 when 'HIGH' then 1 when 'MEDIUM' then 2 else 3 end, r."timestamp" desc
                limit %s""", [fid, limit])


def q_moisture_daily(fid, days=7):
    return ("""select date_trunc('day', r."timestamp" at time zone 'Asia/Kolkata')::date as day, round(avg(r.value), 2) as avg
                 from sensor_readings r join sensors s using (sensor_id) join fields f using (field_id)
                where f.farmer_id = %s and s.sensor_type = 'SOIL_MOISTURE' and r.status = 'GOOD'
                  and r."timestamp" > now() - make_interval(days => %s)
                group by 1 order by 1""", [fid, days])


def q_water_by_field(fid, days=7):
    return ("""select f.field_id, f.field_name, coalesce(sum(l.water_amount), 0) as litres
                 from fields f left join irrigation_logs l
                   on l.field_id = f.field_id and l."timestamp" > now() - make_interval(days => %s)
                where f.farmer_id = %s group by f.field_id, f.field_name order by f.field_id""", [days, fid])


def q_thresholds(fid):
    return ("select * from thresholds where farmer_id = %s", [fid])


def q_field_sensors(field_id):
    return ("""select sensor_id, sensor_type, unit, health, last_reading, last_reading_at
                 from v_sensor_status where field_id = %s order by sensor_type""", [field_id])


def q_series(field_id, hours):
    bucket = 1 if hours <= 24 else 6 if hours <= 168 else 24          # hourly / 6-hourly / daily averages
    return ("""select s.sensor_type,
                      to_timestamp(floor(extract(epoch from r."timestamp") / (%s * 3600)) * (%s * 3600)) as t,
                      round(avg(r.value), 2) as v
                 from sensor_readings r join sensors s using (sensor_id)
                where s.field_id = %s and r."timestamp" > now() - make_interval(hours => %s)
                group by 1, 2 order by 1, 2""", [bucket, bucket, field_id, hours])


def q_yields(fid):
    return ("""with mine as (
                 select c.season_year as year, round(avg(c.yield_q_per_acre), 1) as yield
                   from crop_records c join fields f using (field_id)
                  where f.farmer_id = %s and c.season_year is not null group by 1),
               district as (
                 select c.season_year as year, round(avg(c.yield_q_per_acre), 1) as district_avg
                   from crop_records c join fields f using (field_id) join farmers fa using (farmer_id)
                  where fa.district = (select district from farmers where farmer_id = %s) and c.season_year is not null group by 1)
               select m.year, m.yield, d.district_avg from mine m left join district d using (year) order by m.year""", [fid, fid])


def q_fertilizer(fid):
    return ("""select l.type, sum(l.amount) as kg, count(*)::int as applications
                 from fertilizer_logs l join fields f using (field_id)
                where f.farmer_id = %s and l."timestamp" > now() - interval '180 days' group by 1 order by 2 desc""", [fid])


def q_water_daily(fid, days):
    return ("""select date_trunc('day', l."timestamp" at time zone 'Asia/Kolkata')::date as day, sum(l.water_amount) as litres
                 from irrigation_logs l join fields f using (field_id)
                where f.farmer_id = %s and l."timestamp" > now() - make_interval(days => %s) group by 1 order by 1""", [fid, days])


def q_compare(fid, days):
    return ("""select f.field_id, f.field_name, f.area_acres, f.soil_type, f.irrigation_method,
                      round(avg(c.yield_q_per_acre), 1) as avg_yield, round(avg(c.brix_value), 2) as avg_brix,
                      (select coalesce(sum(water_amount), 0) from irrigation_logs l
                        where l.field_id = f.field_id and l."timestamp" > now() - make_interval(days => %s)) as water_litres
                 from fields f left join crop_records c using (field_id)
                where f.farmer_id = %s group by f.field_id order by f.field_id""", [days, fid])


# --------------------------------------------------------------------------- screen loaders (1 round trip each)
def dashboard(fid):
    b = bundle(summary=q_summary(fid), fields=q_fields(fid), alerts=q_alerts(fid), water=q_water_by_field(fid),
               trend=q_moisture_daily(fid), thresholds=q_thresholds(fid))
    b["summary"], b["thresholds"] = b["summary"][0], b["thresholds"][0]
    return b


def sensors_fields(fid):
    b = bundle(fields=q_fields(fid), thresholds=q_thresholds(fid))
    return b["fields"], b["thresholds"][0]


def sensors_data(field_id, hours):
    b = bundle(series=q_series(field_id, hours), sensors=q_field_sensors(field_id))
    out = {"SOIL_MOISTURE": [], "TEMPERATURE": [], "HUMIDITY": []}
    for r in b["series"]:
        out[r["sensor_type"]].append(r)
    return out, b["sensors"]


def analytics(fid, days=30):
    return bundle(yields=q_yields(fid), fertilizer=q_fertilizer(fid), water_daily=q_water_daily(fid, days),
                  compare=q_compare(fid, days))


def thresholds(fid):
    return one(*q_thresholds(fid))


def fields_summary(fid):
    return rows(*q_fields(fid))


# --------------------------------------------------------------------------- recommendations
def recommendations(farmer_id, status="PENDING", rec_type=None, limit=100):
    return rows(
        """select r.*, f.field_name from recommendations r join fields f using (field_id)
            where f.farmer_id = %s and (%s = 'ALL' or r.status = %s) and (%s::text is null or r.type = %s)
            order by case when r.status = 'PENDING' then
                        case r.priority when 'CRITICAL' then 0 when 'HIGH' then 1 when 'MEDIUM' then 2 else 3 end end,
                     r."timestamp" desc
            limit %s""", (farmer_id, status, status, rec_type, rec_type, limit))


def apply_recommendation(rec_id, farmer_id):
    """Mark advice as done AND write the matching irrigation / fertilizer log — one transaction."""
    with transaction() as cur:
        cur.execute(
            """select r.*, f.irrigation_method from recommendations r join fields f using (field_id)
                where r.rec_id = %s and f.farmer_id = %s for update of r""", (rec_id, farmer_id))
        rec = cur.fetchone()
        if not rec:
            raise DatabaseError("Recommendation not found.")
        if rec["status"] != "PENDING":
            raise DatabaseError(f"This recommendation is already {rec['status'].lower()}.")
        details = rec["details"] or {}
        log_type = None
        if rec["type"] == "IRRIGATION":
            plan = details.get("plan") or {}
            cur.execute(
                """insert into irrigation_logs (field_id, rec_id, duration, water_amount, method, notes)
                   values (%s, %s, %s, %s, %s, 'Applied from SoilSense desktop')""",
                (rec["field_id"], rec_id, min(1440, plan.get("duration_min") or 60),
                 plan.get("water_litres") or 1, rec["irrigation_method"]))
            log_type = "irrigation"
        elif rec["type"] == "FERTILIZER":
            cur.execute(
                """insert into fertilizer_logs (field_id, rec_id, type, amount, notes)
                   values (%s, %s, %s, %s, 'Applied from SoilSense desktop')""",
                (rec["field_id"], rec_id, details.get("product"), details.get("amount_kg") or 1))
            log_type = "fertilizer"
        cur.execute("update recommendations set status = 'APPLIED', resolved_at = now() where rec_id = %s", (rec_id,))
    return log_type


def dismiss_recommendation(rec_id, farmer_id, reason=""):
    with transaction() as cur:
        cur.execute(
            """update recommendations r set status = 'DISMISSED', resolved_at = now(),
                      details = r.details || jsonb_build_object('dismiss_reason', %s::text)
                 from fields f
                where r.field_id = f.field_id and r.rec_id = %s and f.farmer_id = %s and r.status = 'PENDING'""",
            (reason or None, rec_id, farmer_id))
        if cur.rowcount == 0:
            raise DatabaseError("This recommendation is no longer pending.")


# --------------------------------------------------------------------------- settings
THRESHOLD_KEYS = ["moisture_critical", "moisture_low", "moisture_target", "moisture_high",
                  "temp_low", "temp_high", "humidity_low", "humidity_high",
                  "nitrogen_min", "phosphorus_min", "potassium_min", "root_zone_mm"]


def update_thresholds(farmer_id, values):
    """The CHECK constraints in the schema enforce the ordering (critical < low < target < high)."""
    keys = [k for k in THRESHOLD_KEYS if k in values]
    sets = ", ".join(f"{k} = %s" for k in keys)          # column names come from the fixed list above
    try:
        with transaction() as cur:
            cur.execute(f"update thresholds set {sets} where farmer_id = %s",
                        [values[k] for k in keys] + [farmer_id])
    except psycopg2.errors.CheckViolation as e:
        raise DatabaseError("Those values break a rule: soil moisture must be critical < low < target < high, "
                            "and each 'low' must be below its 'high'.") from e


def field_ids(farmer_id):
    return [r["field_id"] for r in rows("select field_id from fields where farmer_id = %s order by field_id", (farmer_id,))]


def to_json(obj):
    return json.dumps(obj, default=str)
