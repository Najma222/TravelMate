# TravelMate Frontend

A lightweight HTML/CSS/JavaScript frontend for TravelMate. This package is separated from the nested repository that was accidentally included in the original ZIP.

## Pages
- `login.html` — sign in
- `register.html` — create account
- `dashboard.html` — dashboard overview
- `trips.html` — trips list
- `trip-new.html` — create trip
- `trip.html` — trip detail view
- `notifications.html` — reminders/notifications

## Assets
- `assets/css/fun.css` — shared styles
- `assets/js/api.js` — API helper
- `assets/js/app.js` — shared frontend utilities

## Run locally
Serve this directory using a static HTTP server (avoid opening pages directly with `file://`). For example, from this folder:

```bash
python -m http.server 8080
```

Then open `http://localhost:8080/login.html`. Configure the API base URL in `assets/js/api.js` for your backend environment.

## Notes
The original HTML filenames are intentionally retained to minimize breakage in existing navigation and scripts. The embedded `TravelMate/` repository from the source archive is not part of this frontend package.
