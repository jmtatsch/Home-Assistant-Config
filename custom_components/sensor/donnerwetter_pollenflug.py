"""
Create virtual Donnerwetter allergen sensors.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.donnerwetter_pollenflug/
"""

import logging
from datetime import timedelta
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle, slugify
from homeassistant.const import (
    ATTR_ATTRIBUTION, ATTR_STATE, CONF_MONITORED_CONDITIONS
)

_LOGGER = logging.getLogger(__name__)

CONF_ZIP_CODE = 'zip_code'
CONF_CITY = 'city'

DEFAULT_ATTRIBUTION = "Data provided by Donnerwetter"
MIN_TIME_UPDATE_OVERVIEW = timedelta(hours=8)
MIN_TIME_UPDATE_DETAILS = timedelta(hours=6)

ALLERGENES = ['Erle', 'Hasel', 'Löwenzahn', 'Gräser', 'Gerste', 'Linde',
              'Beifuß', 'Gänsefuß', 'Mais', 'Brennessel', 'Hafer', 'Roggen',
              'Weizen', 'Spitzwegerich', 'Raps', 'Hopfen', 'Holunder', 'Ulme',
              'Pappel', 'Weide', 'Birke', 'Eiche', 'Esche', 'Platane',
              'Flieder', 'Ambrosia', 'Buche', 'Rotbuche', 'Ahorn', 'Nessel',
              'Kiefer', 'Tanne', 'Fichte']

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_CITY): cv.string,
    vol.Required(CONF_ZIP_CODE): cv.string,
    vol.Required(CONF_MONITORED_CONDITIONS):
    vol.All(cv.ensure_list, [vol.In(ALLERGENES)]),
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the sensor platform."""

    city = config.get(CONF_CITY)
    zip_code = config.get(CONF_ZIP_CODE)
    allergenes = config.get(CONF_MONITORED_CONDITIONS)

    data_manager = DonnerwetterDataManager(zip_code, city)
    sensors = []
    for allergen in allergenes:
        sensors.append(PollenflugSensor(data_manager, allergen))
    add_devices(sensors)


class DonnerwetterDataManager(object):
    """The Donnerwetter DataManager responsible for parsing and caching data."""

    def __init__(self, zip_code, city):
        """Initialize the DataManager."""
        self._zip_code = zip_code
        self._city = city
        self._data = None
        self.update()

    @Throttle(MIN_TIME_UPDATE_OVERVIEW)
    def update(self):
        """Parse the overview data from donnerwetter and update the data."""
        import urllib
        from bs4 import BeautifulSoup
        args = {'plz': self._zip_code}
        site = urllib.request.urlopen("http://donnerwetter.de/pollen/region.hts?{}".format(urllib.parse.urlencode(args)))
        soup = BeautifulSoup(site.read(), "html5lib")
        table = soup.find("table", {"width": "400"})
        data = {}
        for row in table.findAll("tr"):
            cells = row.findAll("td")
            allergen = None
            strength = None
            for cell in cells:
                if cell.text not in ["Verlauf\n         Langfrist\n        ", " ", "", "\xa0\xa0"]:
                    allergen = cell.text
                try:
                    strength = cell.img['alt']
                    data[allergen] = strength

                except (KeyError, TypeError) as err:
                    pass
        _LOGGER.debug('Received overview data: %s', data)
        self._data = data

    @Throttle(MIN_TIME_UPDATE_DETAILS)
    def get_hourly_details(self, allergen, strength):
        """Get the hourly forecast for an allergen."""
        import urllib
        from bs4 import BeautifulSoup
        args = {'Ort': self._city, 'Allergen': allergen, 'Staerke': strength}
        site = urllib.request.urlopen("https://www.donnerwetter.de/pollenflug/verlauf.hts?{}".format(urllib.parse.urlencode(args)))
        html = site.read()
        soup = BeautifulSoup(html, "html5lib")
        table = soup.find("table", {"cellpadding": "2"})

        data = {}
        hour = 4
        for row in table.findAll("tr"):
            cells = row.findAll("td")
            allergen = None
            strength = None
            for cell in cells:
                try:
                    strength = float(cell.img['height'])
                    if strength < 150:
                        data[hour] = strength
                        hour += 1

                except (KeyError, TypeError) as err:
                    pass
        _LOGGER.debug('Received detail data: %s', data)
        return data


class PollenflugSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, data_manager, allergen):
        """Initialize the sensor."""
        self._data_manager = data_manager
        self._allergen = allergen
        self._state = data_manager._data[allergen]
        self._icon = 'mdi:flower'
        self._unit = None
        self._unique_id = data_manager._zip_code

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._allergen

    @property
    def unique_id(self):
        """Return a unique, HASS-friendly identifier for this entity."""
        return '{0}_{1}'.format(self._unique_id, slugify(self._allergen))

    @property
    def icon(self):
        """Return the icon."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attr = {ATTR_ATTRIBUTION: DEFAULT_ATTRIBUTION}
        return attr

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        self._data_manager.update()
        self._state = self._data_manager[self._allergen]

