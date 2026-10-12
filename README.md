# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route. It compares three routes, checks the forecast at every checkpoint for the time the truck will actually be there, applies the load-weight rules, and recommends a route. A 48-hour heatmap shows how the weather moves along the corridor.

**Live app:** _link added after deploy_ · **Walkthrough:** _Loom link_

![Route comparison with risk-coloured routes and the corridor heatmap](docs/screenshot.png)

## What it does

- **Input:** origin and destination (search or `lat, lon`), departure time, load weight, checkpoint spacing (10 / 25 / 50 mi), and optional hours-of-service breaks.
- **Three routes** from TomTom's truck router (weight-aware roads, truck travel times).
- **Checkpoints** every 10, 25 or 50 miles, each with its own ETA and the forecast for that hour: wind, gusts, rain, snow and temperature.
- **Risk** for each checkpoint from the spec's tables, including the load rules, with the condition that caused it.
- **Recommendation** using the spec's order, and a plain sentence explaining why it won.
- **Map** with every route coloured by risk, checkpoints, rest stops, popups, and trucks that move with the time slider.
- **Heatmap** of risk, wind, rain or snow in a 30-mile corridor around the routes, for 0–48 h after departure, with play/pause.

## How it works

```
POST /api/plan
  1. Routes       TomTom truck routing, gross weight = 35,000 lb tare + load, up to 3 alternatives.
                  If TomTom returns fewer, extra routes are forced through detour points on either
                  side of the fastest route and kept only if they're distinct and <= 1.6x as slow.
  2. Checkpoints  mile 0, every N miles, and the destination.
  3. ETAs         from TomTom's per-point travel times (so city stretches are slower than interstate),
                  plus FMCSA breaks if enabled.
  4. Weather      one batched Open-Meteo request set for every checkpoint on every route,
                  sampled at each checkpoint's ETA.
  5. Risk         wind / rain / snow bands + load rules -> worst of the three.
  6. Ranking      No Travel miles -> Severe miles -> High miles -> average risk -> travel time.

POST /api/corridor   (fired right after the plan, so routes appear first)
  Grid of forecast points within 30 mi of the routes, 49 hourly values each, plus risk per hour.
  The browser turns it into a smooth image and redraws it as the slider moves.
```

## Spec interpretations

The brief leaves a few things open. These are the choices made, and they're all in code with tests.

| Topic | What the app does |
|---|---|
| Band edges | The tables share end points ("0.10–0.25", "0.25–0.50"), so each band starts at its lower bound: 0.25 in/hr of rain is High. No Travel follows the table exactly: ≥55 mph wind, but rain **>** 1.00 and snow **>** 3.0, so 1.00 in/hr of rain is still Severe. (`backend/trips/domain/risk.py`) |
| Load rules | "Over 30,000 lb" and "over 40,000 lb" are strict. The rules only raise the wind level. A checkpoint's level is the worst of wind (after load rules), rain and snow. |
| Load weight | Taken as cargo weight, as the load rules imply. Routing gets the gross weight (35,000 lb tare + load). |
| Wind | Sustained 10 m wind, which is what the thresholds describe. Gusts are shown but not scored. |
| Rain / snow rate | Open-Meteo's hourly totals in inches: rain + showers for rain, snowfall (snow depth, not water equivalent) for snow. |
| Weather timing | Wind and temperature are instantaneous, so they're interpolated to the exact ETA. Precipitation totals cover the hour *ending* at each timestamp, so a truck at 14:37 gets the 14:00–15:00 total. |
| "Severe miles" | Each checkpoint stands for the road from the midpoint with the previous checkpoint to the midpoint with the next one. These stretches add up to the route length exactly. |
| No Travel | Not in the spec's ranking list, but it's worse than Severe, so No Travel miles are compared first. If every route has some, the app says no route is safe and recommends the least-exposed one. |
| Average risk | Distance-weighted, with Low = 0 to No Travel = 4. |
| Ties | Miles are compared at 0.1 mi and average risk at 0.01. Smaller differences are sampling noise, so the next rule decides, finally travel time. |
| ETAs and HOS | A 20-hour drive can't finish in 20 hours. With breaks on, ETAs include a 30-minute break after 8 hours of driving and a 10-hour rest after 11, with the driver starting fully rested. The 60/70-hour weekly limit depends on the driver's history, so it's out of scope. Breaks can be turned off. |
| "Travel time" | Wall-clock trip time, including breaks. |
| Heatmap window | Hours 0–48 starting at the departure hour, so the slider shows the weather the trip will meet. Trucks on the map show where each route's truck is at that time. |
| Departure | From now (30 minutes of grace) up to 7 days ahead, so the whole trip stays inside the 16-day forecast. |

## Performance

- **Fast first result.** Routes, checkpoints and the recommendation come back in one call. The heatmap data loads in a second call while the routes are already on screen.
- **Few upstream calls.** All checkpoints for all three routes go to Open-Meteo in batches of 100 (POST), after snapping to a ~2 km grid to remove duplicates where routes overlap. Forecasts, place searches and whole plans are cached.
- **Bounded heatmap cost.** Grid cells sit on a fixed global lat/lon grid, so cells are cacheable across trips. The cell size grows (0.1° to 1°) until the corridor fits in 600 points, so a cross-country trip costs no more than a short one.
- **Smooth slider.** Which grid cells and weights feed each heatmap pixel is worked out once per trip. A frame is then one pass over the image's pixels (about 70k for a 1,000-mile trip, ~2 ms), blending the two nearest forecast hours. That's what lets the slider glide in 15-minute steps. The image goes straight into a MapLibre image source with no network or PNG encoding. Image rows are spaced in Web Mercator so the overlay lines up at every zoom, and a soft-edged mask drawn along the routes shapes the corridor.
- **Cheap map interactions.** Selecting or hovering a route only swaps layer filters; route data is uploaded once. MapLibre (~280 kB gzipped) is a separate chunk loaded with the map, so the form renders first.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/config` | Routing provider in use and the risk tables (the UI legend reads them). |
| `GET /api/geocode?q=denver` | Place search: TomTom when keyed, otherwise Photon (OpenStreetMap). |
| `POST /api/plan` | `{origin:{lat,lon,label}, destination, departure, load_weight_lb, interval_miles, rest_breaks}` returns routes with checkpoints, risk miles, stops, truck positions every 15 min, and the recommendation. |
| `POST /api/corridor` | `{lines, departure, load_weight_lb}` returns the heatmap grid: cell rows/cols, 49 times, and per-hour wind, rain, snow and risk. |

Errors come back as `{"error": "..."}`, with `"fields"` for validation problems. No route is a 422; an upstream outage or quota limit is a 502 or 503 with a readable message. The plan, corridor and geocode endpoints are rate-limited per IP.

## Run it locally

Requires Python 3.12+ and Node 22+.

```bash
# API on :8000
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # add TOMTOM_API_KEY (free, no card) for truck routing
python manage.py runserver

# UI on :5173 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Without a TomTom key the app still runs. It falls back to the public OSRM demo server and Photon for search, and shows a notice, because OSRM has only a car profile.

## Tests

```bash
cd backend && pytest                 # 128 tests: risk bands, load rules, HOS, checkpoints, ranking,
                                     # weather timing, providers (mocked HTTP), API end to end
cd frontend && npm test              # heatmap layout, sampling, colour ramps, time blending
```

The API tests drive the whole pipeline with fake routes and weather. One example: a 50 mph wind band crossed by two of three routes gives No Travel for a 35,000 lb load, so the third route is recommended, while the same wind with a 20,000 lb load is only Severe. Another test checks that weather is read at each checkpoint's ETA, not at departure. CI runs lint, type checks, tests and the build on every push.

## Deployment

Two Vercel projects from this repo:

- `backend/`: Django as a Python function (Vercel detects `manage.py`). Env: `TOMTOM_API_KEY`.
- `frontend/`: the Vite build. `vercel.json` proxies `/api/*` to the backend, so the browser only talks to one origin and no CORS is needed.

## Layout

```
backend/
  trips/domain/      pure logic, no I/O: risk.py, checkpoints.py, hos.py, recommend.py, corridor.py, geo.py
  trips/services/    routing/ (TomTom, OSRM, alternatives), weather.py (Open-Meteo), geocoding.py, planner.py
  trips/views.py     DRF endpoints, serializers.py validation
frontend/src/
  map/               MapView (MapLibre), layers, GeoJSON builders
  heatmap/           grid -> image: raster.ts (sampling, blending), colors.ts (ramps), renderer.ts
  components/        form, route cards, checkpoint timeline, slider, legend
```

## Limitations

- Open-Meteo's free tier allows about 10,000 location-forecasts a day per server IP. Caching keeps normal use well under that. Setting `OPEN_METEO_API_KEY` switches to the paid endpoint.
- The cache is per process (in memory). On a serverless host each instance warms its own. A shared Redis cache would be the next step.
- Forecasts come from the best available model at each location. Heatmap cells on long trips can be ~30 km, so small storm cells look blocky. Checkpoint risk always uses a point forecast at the checkpoint itself.
- The HOS model covers a single trip from a fresh start, not the weekly cycle or split sleeper berth.
