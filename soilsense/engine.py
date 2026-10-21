"""
Recommendation engine — threshold rules that turn sensor readings into advice.
(Python port of the website's backend/src/services/engine.js, so both give the same advice.)

Input  : last 24 h of readings for a field, the farmer's thresholds, the latest soil test,
         and recent irrigation / fertilizer logs.
Output : recommendations, each with a plain-language explanation, saved to the
         `recommendations` table.

Missing data: use the newest GOOD reading if it is ≤ 6 h old; if the newest rows are MISSING
but a good one exists within 6 h, carry it forward (lower confidence); otherwise the input is
UNAVAILABLE — rules that need it are skipped and a sensor alert is raised instead.

Idempotent: one PENDING recommendation per (field, rule) — re-running updates it, and PENDING
advice whose rule no longer fires is marked EXPIRED.
"""
import json
import math
from datetime import datetime, timezone

from . import db

FRESH_HOURS = 6
IRRIGATION_COOLDOWN_H = 12
FERTILIZER_COOLDOWN_D = 21
M2_PER_ACRE = 4046.86
EFFICIENCY = {"Flood": 0.6, "Sprinkler": 0.75, "Drip": 0.9}          # dictionary: method → efficiency

NUTRIENTS = {
    "N": dict(label="Nitrogen", col="nitrogen_kg_acre", min="nitrogen_min", product="Urea", fraction=0.46, cap=65,
              why="Nitrogen drives tillering and cane elongation."),
    "P": dict(label="Phosphorus", col="phosphorus_kg_acre", min="phosphorus_min", product="DAP", fraction=0.46, cap=50,
              why="Phosphorus supports root development and early tiller strength."),
    "K": dict(label="Potassium", col="potassium_kg_acre", min="potassium_min", product="MOP", fraction=0.60, cap=40,
              why="Potassium improves sucrose accumulation (Brix) and drought tolerance."),
}


def _r(v, d=1):
    return None if v is None else round(float(v), d)


def _num(v):
    return None if v is None else float(v)


def slope_per_hour(points):
    """Least-squares slope (units per hour) of [(datetime, value), ...]."""
    if len(points) < 4:
        return None
    t0 = points[0][0].timestamp()
    xs = [(t.timestamp() - t0) / 3600 for t, _ in points]
    ys = [v for _, v in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def summarise_sensor(sensor, rows, now):
    """rows: newest first, last 24 h."""
    good = [r for r in rows if r["status"] == "GOOD"]
    latest = good[0] if good else None
    streak = next((i for i, r in enumerate(rows) if r["status"] == "GOOD"), -1)
    age_h = (now - latest["timestamp"]).total_seconds() / 3600 if latest else math.inf
    quality = "UNAVAILABLE"
    if latest and age_h <= FRESH_HOURS:
        quality = "CARRIED_FORWARD" if streak > 0 else "OK"
    pts = [(r["timestamp"], float(r["value"])) for r in reversed(good)]
    return {
        "sensorId": sensor["sensor_id"] if sensor else None,
        "value": None if quality == "UNAVAILABLE" else float(latest["value"]),
        "readingAt": latest["timestamp"].isoformat() if latest else None,
        "ageHours": _r(age_h) if math.isfinite(age_h) else None,
        "missingStreak": len(rows) if streak == -1 else streak,
        "missingPct24h": _r(100 * (len(rows) - len(good)) / len(rows), 0) if rows else 100,
        "trendPerHour": _r(slope_per_hour(pts), 3) if slope_per_hour(pts) is not None else None,
        "quality": quality,
    }


def load_contexts(cur, field_ids):
    """Everything the rules need for MANY fields in 6 queries (not 6 per field)."""
    now = datetime.now(timezone.utc)
    cur.execute("select f.*, t.* from fields f join thresholds t using (farmer_id) where f.field_id = any(%s)", (field_ids,))
    fields = {r["field_id"]: {k: (float(v) if hasattr(v, "as_tuple") else v) for k, v in r.items()}   # Decimal → float
              for r in cur.fetchall()}
    cur.execute("""select field_id, sensor_id, sensor_type from sensors
                    where field_id = any(%s) and is_active order by sensor_id""", (field_ids,))
    sensors = cur.fetchall()
    cur.execute("""select sensor_id, value, "timestamp", status from sensor_readings
                    where sensor_id = any(%s) and "timestamp" > now() - interval '24 hours'
                    order by "timestamp" desc""", ([s["sensor_id"] for s in sensors],))
    by_sensor = {}
    for r in cur.fetchall():                                          # dict of lists: sensor → its readings
        by_sensor.setdefault(r["sensor_id"], []).append(r)
    cur.execute("""select distinct on (field_id) field_id, record_id, season_year,
                          nitrogen_kg_acre, phosphorus_kg_acre, potassium_kg_acre
                     from crop_records
                    where field_id = any(%s) and (nitrogen_kg_acre is not null or phosphorus_kg_acre is not null
                                                  or potassium_kg_acre is not null)
                    order by field_id, season_year desc nulls last, harvesting_date desc nulls last""", (field_ids,))
    soil = {r["field_id"]: r for r in cur.fetchall()}
    cur.execute("""select field_id, max("timestamp") as last from irrigation_logs
                    where field_id = any(%s) group by field_id""", (field_ids,))
    last_irr = {r["field_id"]: r["last"] for r in cur.fetchall()}
    cur.execute("""select distinct field_id, type from fertilizer_logs
                    where field_id = any(%s) and "timestamp" > now() - make_interval(days => %s)""",
                (field_ids, FERTILIZER_COOLDOWN_D))
    fert_recent = {}
    for r in cur.fetchall():
        fert_recent.setdefault(r["field_id"], set()).add(r["type"])   # a set: O(1) "was this applied recently?"

    contexts = {}
    for fid, field in fields.items():
        inputs = {}
        for kind in ("SOIL_MOISTURE", "TEMPERATURE", "HUMIDITY"):
            s = next((x for x in sensors if x["field_id"] == fid and x["sensor_type"] == kind), None)
            inputs[kind] = (summarise_sensor(s, by_sensor.get(s["sensor_id"], []), now)
                            if s else {"sensorId": None, "value": None, "quality": "NO_SENSOR"})
        contexts[fid] = dict(now=now, field=field, inputs=inputs, soil=soil.get(fid),
                             last_irr=last_irr.get(fid), fert_recent=fert_recent.get(fid, set()))
    return contexts


def irrigation_plan(field, current, target):
    deficit = max(0.0, target - current)
    net_mm = deficit / 100 * field["root_zone_mm"]                    # mm of water over the field
    area_m2 = field["area_acres"] * M2_PER_ACRE
    eff = EFFICIENCY.get(field["irrigation_method"], 0.6)
    litres = net_mm * area_m2 / eff                                   # 1 mm on 1 m² = 1 litre
    minutes = min(1440, max(1, round(litres / field["pump_flow_lph"] * 60)))
    return {"deficit_pct": _r(deficit), "net_depth_mm": _r(net_mm), "efficiency": eff,
            "water_litres": round(litres), "duration_min": minutes,
            "split_sessions": math.ceil(minutes / 720) if minutes > 720 else 1}


def fmt_litres(l):
    return f"{round(l / 1000):,} kL" if l >= 1e5 else f"{round(l):,} L"


def fmt_duration(m):
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h" + (f" {m % 60} min" if m % 60 else "")


def evaluate(ctx):
    """Pure rules → list of candidate recommendations (dicts)."""
    f, inp, soil, now = ctx["field"], ctx["inputs"], ctx["soil"], ctx["now"]
    M, T, H = inp["SOIL_MOISTURE"], inp["TEMPERATURE"], inp["HUMIDITY"]
    out = []                                                          # dynamic array: rules append what fires
    conf = lambda i: "high" if i["quality"] == "OK" else "reduced"
    note = lambda i, label: (f" Note: the latest {i['missingStreak']} {label} reading(s) were missing, so the last "
                             f"good value from {i['ageHours']} h ago was used.") if i["quality"] == "CARRIED_FORWARD" else ""

    # sensor health
    for kind, i, label in (("SOIL_MOISTURE", M, "soil-moisture"), ("TEMPERATURE", T, "temperature"), ("HUMIDITY", H, "humidity")):
        if i["quality"] == "UNAVAILABLE":
            out.append(dict(
                type="ALERT", rule_code=f"SENSOR_{kind}", priority="HIGH" if kind == "SOIL_MOISTURE" else "MEDIUM",
                action=f"Check the {label} sensor ({i['sensorId']}) — no valid data for "
                       f"{str(i['ageHours']) + ' h' if i['ageHours'] else 'over 24 h'}",
                explanation=f"No good {label} reading has arrived in the last {FRESH_HOURS} hours "
                            f"({i['missingPct24h']}% of readings in the last 24 h were missing). " +
                            ("Irrigation advice for this field is paused until the sensor reports again — check the battery, "
                             "cable and that the probe is still in the soil." if kind == "SOIL_MOISTURE"
                             else "Advice that depends on this sensor is paused. Check the battery and the sensor housing."),
                details={"sensor_id": i["sensorId"], "last_good_at": i["readingAt"], "missing_pct_24h": i["missingPct24h"]}))

    # irrigation
    recent = ctx["last_irr"] and (now - ctx["last_irr"]).total_seconds() / 3600 < IRRIGATION_COOLDOWN_H
    if M["value"] is not None and not recent:
        m = M["value"]
        hot = T["value"] is not None and T["value"] >= f["temp_high"]
        if m < f["moisture_low"]:
            plan = irrigation_plan(f, m, f["moisture_target"])
            critical = m < f["moisture_critical"]
            out.append(dict(
                type="IRRIGATION", rule_code="IRR_CRITICAL" if critical else "IRR_LOW",
                priority="CRITICAL" if critical else "HIGH" if hot else "MEDIUM",
                action=f"{'Irrigate now' if critical else 'Irrigate today'}: about {fmt_litres(plan['water_litres'])} "
                       f"({fmt_duration(plan['duration_min'])} of pumping)" +
                       (f" in {plan['split_sessions']} sessions" if plan["split_sessions"] > 1 else ""),
                explanation=f"Soil moisture is {_r(m)}%, below your "
                            f"{'critical level of ' + str(f['moisture_critical']) if critical else 'irrigation threshold of ' + str(f['moisture_low'])}%. "
                            f"Bringing the {f['root_zone_mm']:.0f} mm root zone back to the {f['moisture_target']}% target needs about "
                            f"{plan['net_depth_mm']} mm of water; with {f['irrigation_method'].lower()} irrigation "
                            f"(≈{round(plan['efficiency'] * 100)}% efficient) on {f['area_acres']} acres that is "
                            f"{fmt_litres(plan['water_litres'])}." +
                            (f" It is also hot ({_r(T['value'])}°C), so irrigate in the early morning or evening." if hot else "") +
                            note(M, "soil-moisture"),
                details={"inputs": {"soil_moisture": m, "temperature": T["value"], "humidity": H["value"]},
                         "thresholds": {"low": f["moisture_low"], "critical": f["moisture_critical"], "target": f["moisture_target"]},
                         "plan": plan, "confidence": conf(M)}))
        elif m > f["moisture_high"]:
            out.append(dict(
                type="ALERT", rule_code="IRR_WATERLOGGING", priority="MEDIUM",
                action="Stop irrigation and open drainage channels",
                explanation=f"Soil moisture is {_r(m)}%, above the {f['moisture_high']}% upper limit. Waterlogged roots get too "
                            "little oxygen, which slows growth and raises the risk of root rot. Skip the next irrigation and "
                            "clear field drains." + note(M, "soil-moisture"),
                details={"inputs": {"soil_moisture": m}, "thresholds": {"high": f["moisture_high"]}, "confidence": conf(M)}))
        elif M.get("trendPerHour") is not None and M["trendPerHour"] < 0:
            hours = (m - f["moisture_low"]) / -M["trendPerHour"]
            if hours <= 24:
                plan = irrigation_plan(f, f["moisture_low"], f["moisture_target"])
                out.append(dict(
                    type="IRRIGATION", rule_code="IRR_FORECAST", priority="LOW",
                    action=f"Plan irrigation within ~{max(1, round(hours))} h (≈{fmt_litres(plan['water_litres'])})",
                    explanation=f"Soil moisture is {_r(m)}% and falling about {_r(-M['trendPerHour'] * 24)}% per day. At this "
                                f"rate it will reach your {f['moisture_low']}% threshold in roughly {round(hours)} hours, so "
                                "schedule water and labour now.",
                    details={"inputs": {"soil_moisture": m, "trend_per_hour": M["trendPerHour"]},
                             "hours_to_threshold": _r(hours), "plan": plan, "confidence": conf(M)}))

    # weather / disease
    if T["value"] is not None and T["value"] >= f["temp_high"]:
        out.append(dict(
            type="ALERT", rule_code="HEAT_STRESS", priority="HIGH" if T["value"] >= f["temp_high"] + 4 else "MEDIUM",
            action="Heat stress: keep soil moist and avoid fertilizer application today",
            explanation=f"Canopy temperature is {_r(T['value'])}°C, above your {f['temp_high']}°C limit. Sugarcane growth slows "
                        "above ~38°C and fertilizer applied to hot, dry soil is easily lost. Prefer light irrigation in the "
                        "evening; consider trash mulching to cool the soil." + note(T, "temperature"),
            details={"inputs": {"temperature": T["value"]}, "thresholds": {"high": f["temp_high"]}, "confidence": conf(T)}))
    if T["value"] is not None and T["value"] <= f["temp_low"]:
        out.append(dict(
            type="ALERT", rule_code="COLD_STRESS", priority="MEDIUM",
            action="Cold spell: give a light irrigation in the evening to protect against frost",
            explanation=f"Temperature is {_r(T['value'])}°C, below your {f['temp_low']}°C limit. Moist soil holds heat "
                        "overnight, which reduces frost damage to young shoots and ratoon buds." + note(T, "temperature"),
            details={"inputs": {"temperature": T["value"]}, "thresholds": {"low": f["temp_low"]}, "confidence": conf(T)}))
    if H["value"] is not None and H["value"] >= f["humidity_high"] and (T["value"] is None or 20 <= T["value"] <= 34):
        out.append(dict(
            type="ALERT", rule_code="DISEASE_RISK", priority="MEDIUM",
            action="High disease risk: scout for red rot and smut; avoid evening irrigation",
            explanation=f"Humidity is {_r(H['value'])}%" + (f" at {_r(T['value'])}°C" if T["value"] is not None else "") +
                        " — warm, humid conditions favour fungal diseases such as red rot and smut. Inspect leaves and "
                        "split a few canes; remove and burn infected clumps." + note(H, "humidity"),
            details={"inputs": {"humidity": H["value"], "temperature": T["value"]},
                     "thresholds": {"humidity_high": f["humidity_high"]}, "confidence": conf(H)}))

    # fertilizer from the latest soil test
    if soil:
        hot = T["value"] is not None and T["value"] >= f["temp_high"]
        for key, n in NUTRIENTS.items():
            level, minimum = _num(soil[n["col"]]), f[n["min"]]
            if level is None or level >= minimum or n["product"] in ctx["fert_recent"]:
                continue
            need = (minimum - level) * f["area_acres"]
            full = need / n["fraction"]
            product = min(full, n["cap"] * f["area_acres"])
            split = full > product + 0.5
            out.append(dict(
                type="FERTILIZER", rule_code=f"FERT_{key}_LOW", priority="HIGH" if level < minimum * 0.7 else "MEDIUM",
                action=f"Apply {round(product)} kg {n['product']} on {f['field_name']}" + (" (first split dose)" if split else ""),
                explanation=f"The latest soil test ({soil['season_year'] or 'most recent season'}) shows {n['label'].lower()} at "
                            f"{_r(level)} kg/acre, below your {minimum} kg/acre minimum. {n['why']} Closing the gap on "
                            f"{f['area_acres']} acres needs ≈{round(full)} kg {n['product']}" +
                            (f"; apply at most {n['cap']} kg/acre at a time, so give {round(product)} kg now and the rest "
                             "after 3–4 weeks." if split else ".") +
                            " Apply on moist soil (after irrigation) and incorporate near the cane rows." +
                            (" Wait until the current heat spell eases." if hot else ""),
                details={"soil_test": {"record_id": soil["record_id"], "season_year": soil["season_year"], "level_kg_acre": level},
                         "threshold": minimum, "product": n["product"], "amount_kg": round(product),
                         "full_requirement_kg": round(full), "split": split}))
    return out


def evaluate_fields(field_ids):
    """Run the rules for several fields and save the results — one transaction, ~8 round trips in total."""
    from psycopg2.extras import execute_values
    if not field_ids:
        return []
    with db.transaction() as cur:
        contexts = load_contexts(cur, field_ids)
        candidates = [(fid, r) for fid, ctx in contexts.items() for r in evaluate(ctx)]
        stats = {fid: {"field_id": fid, "created": 0, "updated": 0, "expired": 0, "inputs": ctx["inputs"]}
                 for fid, ctx in contexts.items()}
        if candidates:
            # one multi-row upsert; the partial unique index keeps ONE pending row per (field, rule)
            res = execute_values(cur, """
                insert into recommendations (field_id, type, priority, action, explanation, details, rule_code)
                values %s
                on conflict (field_id, rule_code) where status = 'PENDING'
                do update set priority = excluded.priority, action = excluded.action,
                              explanation = excluded.explanation, details = excluded.details
                returning field_id, (xmax = 0) as inserted""",
                [(fid, r["type"], r["priority"], r["action"], r["explanation"], json.dumps(r["details"], default=str),
                  r["rule_code"]) for fid, r in candidates], fetch=True)
            for row in res:
                stats[row["field_id"]]["created" if row["inserted"] else "updated"] += 1
        # pending advice whose rule no longer fires → EXPIRED
        firing = [f"{fid}|{r['rule_code']}" for fid, r in candidates] or [""]
        cur.execute("""update recommendations set status = 'EXPIRED', resolved_at = now()
                        where field_id = any(%s) and status = 'PENDING'
                          and not ((field_id || '|' || rule_code) = any(%s))
                    returning field_id""", (list(contexts), firing))
        for row in cur.fetchall():
            stats[row["field_id"]]["expired"] += 1
    return list(stats.values())


def evaluate_field(field_id):
    res = evaluate_fields([field_id])
    return res[0] if res else None


def evaluate_farmer(farmer_id):
    results = evaluate_fields(db.field_ids(farmer_id))
    return {"fields": len(results), "created": sum(r["created"] for r in results),
            "expired": sum(r["expired"] for r in results)}
