"""CatholicCalendar calendar"""
from __future__ import annotations

import logging
import datetime
import urllib.parse


from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .calendar_generator import CalendarGenerator

_LOGGER = logging.getLogger(__name__)

__version__ = "1.0.1"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the CatholicCalendar platform from a UI config entry."""
    name = entry.title or "Catholic Calendar"
    
    async_add_entities(
        [
            CatholicCalendar(
                name=name,
                unique_id=entry.entry_id,
            ),
        ],
        update_before_add=True,
    )


class CatholicCalendar(CalendarEntity):
    """Representation of a Catholic Calendar."""

    def __init__(self, name: str, unique_id: str) -> None:
        """Initialize the calendar."""
        self._attr_name = name
        self._attr_unique_id = unique_id
        
        self._attr_device_info = {
            "identifiers": {("catholic_calendar", unique_id)},
            "name": name,
            "manufacturer": "Catholic Calendar",
            "entry_type": "service",
        }
        
        self._years_loaded: list[int] = []
        self._events: list[CalendarEvent] = []

    async def async_load_year(self, year: int) -> None:
        """Run the heavy synchronous generator in a background thread."""
        if year in self._years_loaded:
            return

        # Instantiate the generator for this specific year
        generator = CalendarGenerator(year)
        
        # Run the heavy file-reading and looping generation in the background executor
        returned_data = await self.hass.async_add_executor_job(
            generator.generate_festivities
        )

        # 1. Normalize the returned data into a flat list of event dictionaries
        normalized_festivities = []
        
        if isinstance(returned_data, dict):
            for key, val in returned_data.items():
                if isinstance(val, list):
                    normalized_festivities.extend(val)
                elif isinstance(val, dict):
                    if "date" not in val:
                        val["date"] = key
                    normalized_festivities.append(val)
        elif isinstance(returned_data, list):
            normalized_festivities = returned_data

    # 2. Process the normalized flat list and deduplicate by (date, summary)
        seen_events = {}

        for festivity in normalized_festivities:
            if not isinstance(festivity, dict):
                continue

            summary = festivity.get("name", "Unknown Liturgical Day")
            date_val = festivity.get("date")
            
            # Convert datetime to date if necessary
            if isinstance(date_val, datetime.datetime):
                date_val = date_val.date()
                
            if not date_val:
                continue

            # Translate raw grade to human-readable rank
            GRADE_MAP = {
                0: "Weekday",
                1: "Commemoration",
                2: "Optional Memorial",
                3: "Memorial",
                4: "Feast",
                5: "Feast of the Lord",
                6: "Solemnity",
                7: "High Solemnity"
            }
            
            raw_grade = festivity.get('liturgical_grade', 0)
            try:
                grade_name = GRADE_MAP.get(int(raw_grade), str(raw_grade))
            except (ValueError, TypeError):
                grade_name = str(raw_grade)

            color = str(festivity.get('liturgical_color', 'Unknown')).capitalize()
            
            # Format date for USCCB URL structure (MMDDYY)
            usccb_date_str = date_val.strftime('%m%d%y')
            usccb_url = f"https://bible.usccb.org/bible/readings/{usccb_date_str}.cfm"
            
            # Build the rich description with Spotify, USCCB, and My Catholic Life links
            encoded_name = urllib.parse.quote(summary)
            desc = (
                f"Vestment Color: {color}\n"
                f"Rank: {grade_name}\n\n"
                f"📖 USCCB Daily Scripture Readings:\n"
                f"{usccb_url}\n\n"
                f"🎧 Listen on Spotify (Catholic Daily Reflections):\n"
                f"https://open.spotify.com/show/2uQGw4NXrRGubjtbeLKiTs\n\n"
                f"🕊️ My Catholic Life! Reflection & Calendar:\n"
                f"https://mycatholic.life/liturgy/liturgical-calendar/\n\n"
                f"🔍 Search My Catholic Life for '{summary}':\n"
                f"https://mycatholic.life/?s={encoded_name}"
            )

            # Unique key for deduplication (Same day + Same title)
            event_key = (date_val, summary.strip().lower())

            # Store / Overwrite with the best available data
            seen_events[event_key] = CalendarEvent(
                summary=summary,
                start=date_val,
                end=date_val + datetime.timedelta(days=1),
                description=desc
            )

        # 3. Push deduplicated events into the final array
        self._events.extend(seen_events.values())

        # 4. Mark the year as loaded and sort chronologically
        self._years_loaded.append(year)
        self._events.sort(key=lambda e: e.start)
    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event for Home Assistant state."""
        if not hasattr(self, "_events") or not self._events:
            return None
        
        curr_date = dt_util.now().date()
        
        for event in self._events:
            event_date = event.start if isinstance(event.start, datetime.date) else event.start.date()
            if event_date >= curr_date:
                return event
                
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        years_needed = set(range(start_date.year, end_date.year + 1))
        
        for year in years_needed:
            if year not in self._years_loaded:
                await self.async_load_year(year)

        calendar_events = []
        for event in self._events:
            event_date = event.start if isinstance(event.start, datetime.date) else event.start.date()
            
            if start_date.date() <= event_date <= end_date.date():
                calendar_events.append(event)
                
        return calendar_events
