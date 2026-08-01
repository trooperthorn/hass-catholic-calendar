"""CatholicCalendar calendar"""
from __future__ import annotations

import logging
import datetime
from datetime import timedelta, timezone

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .calendar_generator import CalendarGenerator
from .liturgical_grade import LiturgicalGrade

_LOGGER: logging.Logger = logging.getLogger(__name__)

__version__ = "1.0.1"

COMPONENT_REPO = "https://github.com/trooperthorn/hass-catholic-calendar"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the CatholicCalendar platform from a UI config entry."""
    
    # We pull the name from the title provided during the UI setup, 
    # instead of looking for it in configuration.yaml
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

# ... Leave your `class CatholicCalendar(CalendarEntity):` and everything below it exactly as it is ...
class CatholicCalendar(CalendarEntity):
    """Representation of a Catholic Calendar."""

    def __init__(self, name: str, unique_id: str) -> None:
        """Initialize the calendar."""
        self._generator = CalendarGenerator(self.hass)
        self._attr_name = name
        self._attr_unique_id = unique_id
        
        # This is the magic block that groups the entity under the Integration page
        self._attr_device_info = {
            "identifiers": {("catholic_calendar", unique_id)},
            "name": name,
            "manufacturer": "Catholic Calendar",
            "entry_type": "service",
        }

        # --- Initialize all tracking variables expected by the legacy code ---
        self._years_loaded: list[int] = []
        self._events = []
        self._festivities = {}
        # ---------------------------------------------------------------------
        # (e.g., setting up your CalendarGenerator, etc.)
        
    def __repr__(self: CatholicCalendar) -> str:
        """Return the representation."""
        return "CatholicCalendar"
#
async def async_load_year(self, year: int) -> None:
        """Run the heavy synchronous generator in a background thread."""
        if year in self._years_loaded:
            return

        # Tell the synchronous generator to calculate this year
        self._generator.set_year(year)
        
        # Run the heavy file-reading and looping generation in the background executor
        festivities = await self.hass.async_add_executor_job(
            self._generator.generate_festivities
        )

        # Parse the returned list into Home Assistant CalendarEvents
        for festivity in festivities:
            summary = festivity.get("name", "Unknown")
            date_val = festivity.get("date")
            
            # Convert datetime to date if the generator returns datetimes
            if isinstance(date_val, datetime.datetime):
                date_val = date_val.date()
                
            if date_val:
                # Store it in the class list
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
        # Safety check: if data isn't loaded yet, do nothing (don't generate!)
        if not hasattr(self, "_events") or not self._events:
            return None
        
        curr_date = dt_util.now().date()
        
        # Iterate over pre-sorted list to find the next event
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
        
        # 1. Determine which years are needed to fulfill the UI request
        years_needed = set(range(start_date.year, end_date.year + 1))
        
        # 2. Trigger background generation for missing years
        for year in years_needed:
            if year not in self._years_loaded:
                await self.async_load_year(year)

        # 3. Filter the pre-calculated list for the requested date range
        calendar_events = []
        for event in self._events:
            event_date = event.start if isinstance(event.start, datetime.date) else event.start.date()
            
            if start_date.date() <= event_date <= end_date.date():
                calendar_events.append(event)
                
        _LOGGER.debug("Retrieved %d events", len(calendar_events))
        return calendar_events

    def __generate_festivities(self, year):
        _LOGGER.debug("Generating dates for year %s", year)
        calendar_generator = CalendarGenerator(year)
        festivities = calendar_generator.generate_festivities()
        self._years_loaded.append(year)
        for key in festivities:
            if key not in self._festivities:
                self._festivities.update({key: []})
            self._festivities[key].extend(festivities[key])

    async def async_load_year(self, year: int) -> None:
        """Run the heavy synchronous generator in a background thread."""
        if year in self._years_loaded:
            return

    # Tell Home Assistant to run the blocking generation on a worker thread
        self._generator.set_year(year) # (Or however your generator accepts the year)
        festivities = await self.hass.async_add_executor_job(
            self._generator.generate_festivities
        )

        # Once the thread finishes, process the results back on the main loop
        for festivity in festivities:
            # Create your summary/description based on the generated data
            summary = festivity.get("name", "Unknown")
            date_val = festivity.get("date")
        
            if date_val:
                self._events.append(
                    CalendarEvent(
                        summary=summary,
                        start=date_val,
                        end=date_val + datetime.timedelta(days=1),
                        description=f"Color: {festivity.get('liturgical_color')} \nGrade: {festivity.get('liturgical_grade')}"
                    )
                )

        self._years_loaded.append(year)
        # Sort events chronologically so the event property works correctly
        self._events.sort(key=lambda e: e.start)  
