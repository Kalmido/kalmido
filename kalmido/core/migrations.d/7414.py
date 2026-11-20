"""(#7414): the API marks an event made by a booking on the public booking page as data from outside (events/v1.py
ev_outside looks the events of a page up in appt_bookings.event_id). New index only: an older version ignores it."""
SCHEMA = """
CREATE INDEX IF NOT EXISTS appt_bookings_event ON appt_bookings(event_id) WHERE event_id IS NOT NULL;
"""
