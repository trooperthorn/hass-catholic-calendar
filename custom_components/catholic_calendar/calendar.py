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
        """Run the heavy synchronous generator and merge live RSS reflections."""
        if year in self._years_loaded:
            return

        # 1. Fetch live RSS reflections for rich text content
        rss_data = await self._fetch_rss_reflections()

        # 2. Generate base liturgical calendar data
        generator = CalendarGenerator(year)
        returned_data = await self.hass.async_add_executor_job(
            generator.generate_festivities
        )

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

        seen_events = {}

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

        for festivity in normalized_festivities:
            if not isinstance(festivity, dict):
                continue

            summary = festivity.get("name", "Unknown Liturgical Day")
            date_val = festivity.get("date")
            
            if isinstance(date_val, datetime.datetime):
                date_val = date_val.date()
                
            if not date_val:
                continue

            raw_grade = festivity.get('liturgical_grade', 0)
            try:
                grade_name = GRADE_MAP.get(int(raw_grade), str(raw_grade))
            except (ValueError, TypeError):
                grade_name = str(raw_grade)

            color = str(festivity.get('liturgical_color', 'Unknown')).capitalize()
            usccb_date_str = date_val.strftime('%m%d%y')
            usccb_url = f"https://bible.usccb.org/bible/readings/{usccb_date_str}.cfm"
            
            # Check if we have a live RSS reflection for this specific date
            rss_entry = rss_data.get(date_val)
            
            if rss_entry:
                # Use the rich reflection post content if available
                reflection_link = rss_entry["link"]
                # Clean up HTML tags if needed, or leave raw for markdown rendering
                reflection_body = rss_entry["content"]
                desc = (
                    f"Vestment Color: {color}\n"
                    f"Rank: {grade_name}\n\n"
                    f"📖 USCCB Daily Readings:\n{usccb_url}\n\n"
                    f"🎧 Listen on Spotify:\nhttps://open.spotify.com/show/2uQGw4NXrRGubjtbeLKiTs\n\n"
                    f"🕊️ Daily Reflection Text:\n{reflection_link}\n\n"
                    f"{reflection_body}"
                )
            else:
                encoded_name = urllib.parse.quote(summary)
                desc = (
                    f"Vestment Color: {color}\n"
                    f"Rank: {grade_name}\n\n"
                    f"📖 USCCB Daily Readings:\n{usccb_url}\n\n"
                    f"🎧 Listen on Spotify:\nhttps://open.spotify.com/show/2uQGw4NXrRGubjtbeLKiTs\n\n"
                    f"🕊️ My Catholic Life! Calendar:\nhttps://mycatholic.life/liturgy/liturgical-calendar/\n\n"
                    f"🔍 Search:\nhttps://mycatholic.life/?s={encoded_name}"
                )

            event_key = (date_val, summary.strip().lower())
            seen_events[event_key] = CalendarEvent(
                summary=summary,
                start=date_val,
                end=date_val + datetime.timedelta(days=1),
                description=desc
            )

        self._events.extend(seen_events.values())
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


    async def _fetch_rss_reflections(self) -> dict:
        """Fetch and parse My Catholic Life RSS feed in a background thread."""
        import urllib.request
        import xml.etree.ElementTree as ET
        from datetime import datetime

        def _pull_and_parse():
            rss_url = "https://catholic-daily-reflections.com/feed/"
            reflections = {}
            try:
                req = urllib.request.Request(
                    rss_url, 
                    headers={'User-Agent': 'HomeAssistant-CatholicCalendar/1.0'}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    xml_data = response.read()
                
                root = ET.fromstring(xml_data)
                channel = root.find('channel')
                if not channel:
                    return reflections

                for item in channel.findall('item'):
                    title_el = item.find('title')
                    pub_date_el = item.find('pubDate')
                    link_el = item.find('link')
                    desc_el = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
                    if desc_el is None:
                        desc_el = item.find('description')

                    if title_el is not None and pub_date_el is not None:
                        title = title_el.text or ""
                        pub_str = pub_date_el.text or ""
                        link = link_el.text if link_el is not None else ""
                        content = desc_el.text if desc_el is not None else ""

                        # Parse standard RSS pubDate (e.g., Sat, 01 Aug 2026 04:00:00 +0000)
                        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
                            try:
                                dt_obj = datetime.strptime(pub_str.strip(), fmt)
                                date_key = dt_obj.date()
                                reflections[date_key] = {
                                    "title": title,
                                    "link": link,
                                    "content": content
                                }
                                break
                            except ValueError:
                                continue
            except Exception as err:
                _LOGGER.error("Failed to fetch My Catholic Life RSS feed: %s", err)
            
            return reflections

        return await self.hass.async_add_executor_job(_pull_and_parse)
