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
    """Representation of a CatholicCalendar calendar."""

    _attr_force_update = True

    def __init__(
        self: CatholicCalendar,
        name: str,
    ) -> None:
        """Initialize the CatholicCalendar calendar."""
        self._attr_name = name
        self._years_loaded: list[int] = []
        self._festivities: dict[datetime.datetime, list[dict[str, str]]] = {}
        _LOGGER.debug("CatholicCalendar initialized - %s", self)

    def __repr__(self: CatholicCalendar) -> str:
        """Return the representation."""
        return "CatholicCalendar"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        curr_date = dt_util.now().date()
        if curr_date.year not in self._years_loaded:
            self.__generate_festivities(curr_date.year)

        events = self.__get_calendar_events(curr_date)
        if len(events) == 0:
            return None
        return events[0]

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        for year in range(start_date.year, end_date.year + 1):
            if year not in self._years_loaded:
                self.__generate_festivities(year)
        calendar_events = []

        curr_date = start_date
        while curr_date <= end_date:
            _LOGGER.debug("getting calender event for date: %s", curr_date)
            calendar_events.extend(self.__get_calendar_events(curr_date))
            curr_date += datetime.timedelta(days=1)

        _LOGGER.debug("retrieved calendar_events: %s", calendar_events)
        return calendar_events

    def __get_calendar_events(self, date) -> list[CalendarEvent]:
        calendar_events = []
        if datetime.datetime(date.year, date.month, date.day) in self._festivities:
            for festivity in sorted(
                self._festivities[datetime.datetime(date.year, date.month, date.day)],
                key=lambda x: x["liturgical_grade"] or 0,
                reverse=True,
            ):
                calendar_events.append(
                    CalendarEvent(
                        start=datetime.date(date.year, date.month, date.day),
                        end=datetime.date(date.year, date.month, date.day),
                        summary=festivity["name"],
                        description=f"liturgical_color: {festivity['liturgical_color']}, liturgical_grade: {LiturgicalGrade.descr(festivity['liturgical_grade'])}",
                    )
                )
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
