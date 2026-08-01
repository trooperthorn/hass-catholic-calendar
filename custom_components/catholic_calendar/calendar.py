"""CatholicCalendar calendar"""
from __future__ import annotations

import logging
import datetime

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
        festivities = await self.hass.async_add_executor_job(
            generator.generate_festivities
        )

        # Parse the returned list into Home Assistant CalendarEvents
        for festivity in festivities:
            summary = festivity.get("name", "Unknown")
            date_val = festivity.get("date")
            
            # Convert datetime to date if the generator returns datetimes
            if isinstance(date_val, datetime.datetime):
                date_val = date_val.date()
                
            if date_val:
                self._events.append(
                    CalendarEvent(
                        summary=summary,
                        start=date_val,
                        end=date_val + datetime.timedelta(days=1),
                        description=f"Color: {festivity.get('liturgical_color', '')}\nGrade: {festivity.get('liturgical_grade', '')}"
                    )
                )

        # Mark the year as loaded and sort chronological
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
        _LOGGER.debug("Fetching events between %s and %s", start_date, end_date)
        
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
